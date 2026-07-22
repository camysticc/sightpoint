"""
image_engine/gemini_helper.py — Shared Gemini Vision Caller
════════════════════════════════════════════════════════════
Every deep-analysis module needs the same three things: read the
image, call Gemini with a module-specific prompt, and robustly parse
whatever JSON comes back (including truncated/malformed responses —
see the same repair pattern used throughout the rest of this project).

Centralising it here means each module file only has to write its own
prompt and its own region-voting logic, not another copy of the HTTP
call and JSON repair pipeline.
"""

import base64
import json
import re
from pathlib import Path

import requests

import sightpoint as sp

MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def analyze_with_gemini(image_path: str, prompt: str, timeout: int = 60) -> dict:
    """
    Send `image_path` + `prompt` to Gemini and return the parsed JSON
    dict. Raises RuntimeError with a clear message on any failure
    (missing key, network error, no valid JSON in the response) —
    callers (each module's analyze()) are expected to catch this and
    degrade to a "not detected" result rather than crashing the whole
    deep-analysis run.
    """
    api_key = getattr(sp, "GEMINI_API_KEY", None)
    if not api_key:
        raise RuntimeError("No Gemini API key configured.")

    ext = Path(image_path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 2048},
    }

    resp = None
    last_err = None
    for model in MODELS:
        try:
            r = requests.post(BASE_URL.format(model), json=payload,
                              headers=headers, timeout=timeout)
            if r.status_code == 200:
                resp = r
                break
            elif r.status_code == 404:
                last_err = "model {} unavailable".format(model)
                continue
            r.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("Timed out waiting for Gemini.")
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response else "?"
            if code == 404:
                continue
            msg = {403: "Invalid API key or quota exceeded.",
                   429: "Rate limit — try again shortly."}.get(code, str(exc))
            raise RuntimeError("HTTP {}: {}".format(code, msg))
        except requests.exceptions.RequestException as exc:
            raise RuntimeError("Network error: {}".format(exc))

    if resp is None:
        raise RuntimeError("All Gemini models unavailable ({}).".format(last_err))

    try:
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected Gemini response shape: {}".format(exc))

    return _parse_json_robust(raw)


def _parse_json_robust(raw: str) -> dict:
    """Same multi-pass repair pattern used elsewhere in this project —
    handles markdown fences, trailing commas, and truncated strings
    without ever raising on a merely-imperfect response."""
    raw = re.sub(r"```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"```", "", raw).strip().strip("`").strip()

    m = re.search(r"\{[\s\S]*\}", raw)
    candidates = []
    if m:
        candidates.append(m.group())
    brace = raw.find("{")
    if brace != -1:
        candidates.append(raw[brace:])
    candidates.append(raw)

    for js in candidates:
        try:
            return json.loads(js)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", js))
        except json.JSONDecodeError:
            pass
        try:
            repaired = js.rstrip().rstrip(",")
            repaired = re.sub(r',\s*"[^"]*$', "", repaired).rstrip(",")
            if repaired.count('"') % 2 != 0:
                repaired += '"'
            opens = repaired.count("[") - repaired.count("]")
            opens_c = repaired.count("{") - repaired.count("}")
            repaired += "]" * max(0, opens) + "}" * max(0, opens_c)
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    raise RuntimeError("No usable JSON in Gemini response:\n{}".format(raw[:300]))


def empty_result(reason: str = "not detected") -> dict:
    """Standard shape for a module that found nothing — every module
    returns this same shape on a miss so the orchestrator/Conflict
    Resolver never has to special-case per-module output formats."""
    return {
        "detected": False,
        "region_votes": {},
        "confidence": 0.0,
        "reasoning": reason,
    }
