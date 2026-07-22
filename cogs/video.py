"""
cogs/video.py — SightPoint AI · Video Analysis Cog
═══════════════════════════════════════════════════
Adds a ▶ VIDEO tab to the SightPointApp notebook.

Features
────────
• Time-based frame extraction  (duration ÷ max_frames = interval)
  Direct seek via CAP_PROP_POS_MSEC — never scans every frame
• Parallel frame geolocation   (all frames sent simultaneously)
  Results appear in the thumbnail grid as each one finishes
• Direction of travel          (first + last frame → Gemini)
• Map pins                     (one per frame, labelled with timestamp)

Dependencies (in addition to sightpoint.py's requirements)
─────────────
    pip install opencv-python-headless

Loaded by main.py:
    from cogs import video
    video.setup(app)            # injects VIDEO tab into app._nb
"""

import threading
import os
import tempfile
import datetime
import base64
import json
import re
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ── optional: cv2 ─────────────────────────────────────────────────
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# ── pull everything we need from the boilerplate (read-only imports) ──
import sightpoint as sp   # theme constants, gemini_geolocate, PIL_AVAILABLE, etc.
PIL_AVAILABLE = sp.PIL_AVAILABLE
if PIL_AVAILABLE:
    from PIL import Image, ImageTk, ImageFilter, ImageEnhance

# ─────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────
def _fmt_ts(sec: float) -> str:
    """Seconds → HH:MM:SS or MM:SS string."""
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return "{:02d}:{:02d}:{:02d}".format(h, m, s) if h else "{:02d}:{:02d}".format(m, s)


def extract_key_frames(video_path: str, max_frames: int = 20,
                       log_cb=None) -> list:
    """
    Extract `max_frames` frames at evenly-spaced timestamps.

    Strategy: interval = duration / max_frames
              seek directly with CAP_PROP_POS_MSEC — never scan.

    Returns list of dicts:
        { path, timestamp_sec, frame_num, label }
    """
    def _log(msg, lvl="INFO"):
        if log_cb:
            try: log_cb(msg, lvl)
            except Exception: pass

    tmp_dir = os.path.join(tempfile.gettempdir(), "sightpoint_frames")
    os.makedirs(tmp_dir, exist_ok=True)
    prefix  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    frames  = []

    # ── cv2 path ──────────────────────────────────────────────
    if CV2_AVAILABLE:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            _log("Cannot open video: {}".format(video_path), "ERROR")
            return []

        fps      = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_f  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_f / fps if fps > 0 else 0.0

        if duration <= 0:
            _log("Cannot determine video duration.", "ERROR")
            cap.release()
            return []

        interval = duration / max_frames
        _log("Video: {:.1f}s  {:.0f}fps  {:,} frames — "
             "1 frame every {:.2f}s".format(duration, fps, total_f, interval))

        for i in range(max_frames):
            # Sample at 10 % into each window to avoid black slate on cut
            target_sec = interval * i + interval * 0.10
            target_sec = min(target_sec, duration - 0.05)

            cap.set(cv2.CAP_PROP_POS_MSEC, target_sec * 1000)
            ret, frame = cap.read()
            if not ret:
                _log("Cannot read frame at {:.2f}s".format(target_sec), "WARN")
                continue

            frame_num = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            fpath = os.path.join(tmp_dir,
                                  "fr_{}_i{:03d}.jpg".format(prefix, i))
            cv2.imwrite(fpath, frame)
            frames.append({
                "path":          fpath,
                "timestamp_sec": round(target_sec, 2),
                "frame_num":     frame_num,
                "label":         _fmt_ts(target_sec),
                "index":         i,
            })
            _log("Frame {:02d} captured @ {}".format(i + 1, _fmt_ts(target_sec)))

        cap.release()

    # ── PIL fallback for GIF ───────────────────────────────────
    elif PIL_AVAILABLE and video_path.lower().endswith(".gif"):
        from PIL import ImageSequence
        gif         = Image.open(video_path)
        total       = getattr(gif, "n_frames", 0)
        ms_per_f    = gif.info.get("duration", 100)
        interval_f  = max(1, total // max_frames)
        _log("GIF: {} frames, sampling every {} frames".format(total, interval_f))
        idx = 0
        for i, frame in enumerate(ImageSequence.Iterator(gif)):
            if i % interval_f != 0:
                continue
            sec   = i * ms_per_f / 1000.0
            fpath = os.path.join(tmp_dir,
                                  "fr_{}_i{:03d}.png".format(prefix, idx))
            frame.convert("RGB").save(fpath)
            frames.append({
                "path":          fpath,
                "timestamp_sec": round(sec, 2),
                "frame_num":     i,
                "label":         _fmt_ts(sec),
                "index":         idx,
            })
            idx += 1
            if idx >= max_frames:
                break
    else:
        _log("cv2 not available and file is not GIF. "
             "Install opencv-python-headless.", "WARN")

    _log("Extracted {} frames.".format(len(frames)), "OK")
    return frames


def gemini_travel_direction(first_path: str, last_path: str,
                             api_key: str, log_cb=None) -> dict:
    """
    Send the first and last video frames together to Gemini and ask it to
    estimate direction of travel, movement type, speed, and route clues.
    """
    import requests as _req

    def _log(msg, lvl="INFO"):
        if log_cb:
            try: log_cb(msg, lvl)
            except Exception: pass

    def _read(p):
        ext  = Path(p).suffix.lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png"}.get(ext, "image/jpeg")
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode(), mime

    b64_first, mime_first = _read(first_path)
    b64_last,  mime_last  = _read(last_path)

    prompt = (
        "FRAME A is the FIRST frame of a video clip. "
        "FRAME B is the LAST frame of the same video clip.\n\n"
        "Analyse both frames and determine:\n"
        "  • The likely start location (FRAME A)\n"
        "  • The likely end location   (FRAME B)\n"
        "  • Direction of travel (compass heading, street direction, etc.)\n"
        "  • Movement type: walking / driving / cycling / boat / static / unknown\n"
        "  • Speed estimate: slow / moderate / fast / unknown\n"
        "  • Any visible route clues (street names, landmarks, signs)\n"
        "  • Confidence in your assessment (0–100)\n\n"
        "Return ONLY raw JSON — no markdown, no fences:\n"
        '{\n'
        '  "start_location": "<best guess for FRAME A>",\n'
        '  "end_location":   "<best guess for FRAME B>",\n'
        '  "direction_of_travel": "<compass direction or description>",\n'
        '  "movement_type": "<walking/driving/cycling/boat/static/unknown>",\n'
        '  "speed_estimate": "<slow/moderate/fast/unknown>",\n'
        '  "route_clues": ["<clue1>", "<clue2>"],\n'
        '  "confidence": <0-100>,\n'
        '  "reasoning": "<2-3 sentence explanation>"\n'
        '}'
    )

    _log("Sending first + last frames to Gemini for direction analysis…")

    models  = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    base    = ("https://generativelanguage.googleapis.com/v1beta/"
               "models/{}:generateContent")
    headers = {"Content-Type": "application/json",
               "x-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime_first, "data": b64_first}},
            {"text": "FRAME A — start of clip"},
            {"inline_data": {"mime_type": mime_last,  "data": b64_last}},
            {"text": "FRAME B — end of clip\n\n" + prompt},
        ]}],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 2048},
    }

    resp = None
    for model in models:
        try:
            r = _req.post(base.format(model), json=payload,
                          headers=headers, timeout=120)
            if r.status_code == 200:
                resp = r
                break
            elif r.status_code == 404:
                _log("Model {} not available, trying next…".format(model), "WARN")
                continue
            r.raise_for_status()
        except _req.exceptions.Timeout:
            raise RuntimeError("Timed out waiting for Gemini.")
        except _req.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response else "?"
            if code == 404:
                continue
            msg = {403: "Invalid API key or quota exceeded.",
                   429: "Rate limit — wait and retry."}.get(code, str(exc))
            raise RuntimeError("HTTP {}: {}".format(code, msg))
        except _req.exceptions.RequestException as exc:
            raise RuntimeError("Network error: {}".format(exc))

    if resp is None:
        raise RuntimeError("All Gemini models unavailable for direction analysis.")

    try:
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected Gemini response: {}".format(exc))

    # Clean and parse
    raw = re.sub(r"```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"```", "", raw).strip().strip("`").strip()
    m   = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise RuntimeError("No JSON in direction response:\n{}".format(raw[:300]))
    try:
        result = json.loads(m.group())
    except json.JSONDecodeError:
        fixed = re.sub(r",\s*([}\]])", r"\1", m.group())
        try:
            result = json.loads(fixed)
        except json.JSONDecodeError as exc:
            raise RuntimeError("JSON parse failed: {}".format(exc))

    _log("Direction: {} → {} ({}%)".format(
        result.get("start_location", "?"),
        result.get("end_location", "?"),
        result.get("confidence", "?")), "OK")
    return result


# ─────────────────────────────────────────────────────────────────
#  DEEP VIDEO FRAME GEOLOCATION
#  Replaces sp.gemini_geolocate for video frames — much richer
#  prompt tuned for motion-blurred footage and UK urban analysis.
# ─────────────────────────────────────────────────────────────────
def gemini_geolocate_video_frame(frame_path: str,
                                  frame_label: str,
                                  api_key: str,
                                  log_cb=None) -> dict:
    """
    Deeply analyse a single video frame for geolocation.

    Goes far beyond the standard prompt:
    • Explicitly handles motion blur / low quality
    • Exhaustive UK-specific indicator checklist
    • Distinguishes visually similar cities (Manchester/Liverpool etc.)
    • Calibrated confidence — won't claim 90 %+ unless evidence is clear
    • Returns heatmap candidates for map overlay
    """
    import requests as _req

    def _log(msg, lvl="INFO"):
        if log_cb:
            try: log_cb(msg, lvl)
            except Exception: pass

    ext  = Path(frame_path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png"}.get(ext, "image/jpeg")
    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    prompt = (
        "You are an expert OSINT geolocation analyst specialising in video forensics.\n"
        "This image is a SINGLE FRAME extracted from a video clip at {}.\n"
        "It may be motion-blurred, compressed, or partially obscured — analyse "
        "EVERY visible detail no matter how small or degraded.\n\n"

        "━━━ PHASE 1 — SCENE READING ━━━\n"
        "Describe exhaustively what you see:\n"
        "• Architecture: building style, era, materials, roofline, windows, doors\n"
        "• Road: surface, markings, lane count, kerb style, junction type\n"
        "• Signage: any partial text — even single letters or colour combos matter\n"
        "• Vegetation: tree species, hedge type, grass condition\n"
        "• Sky / lighting: overcast vs sunny, shadows, time of day\n"
        "• People: clothing, uniforms, crowd density\n"
        "• Vehicles: make, model, colour, number plate fragments, bus/tram livery\n\n"

        "━━━ PHASE 2 — OSINT INDICATORS ━━━\n"
        "Check EVERY one of the following, even if only partially visible:\n\n"

        "TRANSPORT:\n"
        "• Bus livery — First (red/orange), Arriva (turquoise), Stagecoach "
        "(orange/red/blue stripes), National Express (white), TfGM (yellow), "
        "Merseytravel (yellow/grey), Go North West (purple)\n"
        "• Trams — Metrolink (grey/yellow, Manchester ONLY), "
        "Merseyrail (silver/yellow, Liverpool underground rail NOT tram), "
        "any tram overhead wires\n"
        "• Taxis — colour and style (Manchester black/white, Liverpool silver)\n"
        "• Number plate fragments — UK format, partial county codes\n"
        "• Railway infrastructure — station canopy style, platform signage\n\n"

        "STREET FURNITURE:\n"
        "• Post boxes — Royal Mail red (pillar vs wall box), "
        "any council or postcode markings on them\n"
        "• Street lights — pole material (concrete vs steel), lamp shape\n"
        "• Bollards — colour, style, any text\n"
        "• Traffic lights — signal head colour, countdown timers, sensor type\n"
        "• Pedestrian crossings — Belisha beacons, zigzag markings, tactile paving\n"
        "• Benches, bins, bus shelters — branding, council logo\n\n"

        "SIGNAGE:\n"
        "• Shop names — national chains (presence/absence narrows region)\n"
        "• Pub names — often hyper-local\n"
        "• Council district signs — 'Welcome to...' boards, bin lorry text\n"
        "• Road signs — font (UK uses Transport font), "
        "ring road / orbital designations (M60=Manchester orbital, etc.)\n"
        "• Football club colours / merchandise / stadium references\n"
        "• University / hospital / NHS trust branding\n\n"

        "UK CITY DISCRIMINATORS (pay special attention when narrowing between "
        "Manchester and Liverpool or other similar Northern English cities):\n"
        "• Liverpool ONLY: Liver Building, Albert Dock red-brick warehouses, "
        "Mersey waterfront, Cunard Building, Lime Street station arches, "
        "Merseyrail yellow trains, Beatles / Cavern Club references, "
        "bold sandstone civic buildings (St George's Hall), L postcode\n"
        "• Manchester ONLY: Metrolink tram overhead wires + yellow/grey trams, "
        "Beetham Tower (blue-glass skyscraper), Northern Quarter brick warehouses, "
        "Arndale Centre yellow/brown tiles, Piccadilly Gardens, canal network + "
        "Bridgewater Canal, M postcode, Victoria / Piccadilly station styles\n"
        "• If you see a TRAM with overhead wires in a Northern English city → "
        "strongly favour Manchester (Metrolink)\n"
        "• If you see the MERSEY RIVER or distinctive waterfront buildings → "
        "strongly favour Liverpool\n\n"

        "CONFIDENCE CALIBRATION:\n"
        "• Only claim 80–100 % if you can see a definitive landmark or clear text\n"
        "• Claim 50–79 % for strong circumstantial evidence "
        "(e.g. Metrolink tram but no text)\n"
        "• Claim 20–49 % for general Northern England with some pointers\n"
        "• Claim <20 % if genuinely uncertain\n"
        "• NEVER output 90 %+ without a specific identifiable element\n\n"

        "━━━ PHASE 3 — TRIANGULATION ━━━\n"
        "Synthesise ALL evidence. Explain your chain of reasoning step by step.\n"
        "Provide 3 weighted candidate locations for the heatmap.\n\n"

        "Return ONLY raw JSON — no markdown, no code fences:\n"
        '{{\n'
        '  "latitude": <float>,\n'
        '  "longitude": <float>,\n'
        '  "location_name": "<City, Country>",\n'
        '  "confidence": <0-100>,\n'
        '  "clues": ["<specific clue 1>","<clue 2>","<clue 3>","<clue 4>","<clue 5>"],\n'
        '  "reasoning": "<step-by-step chain of evidence, 4-6 sentences>",\n'
        '  "country": "<country>",\n'
        '  "city": "<city or district>",\n'
        '  "osint": {{\n'
        '    "license_plate": "<fragment or not visible>",\n'
        '    "bus_livery": "<operator and colours or not visible>",\n'
        '    "tram_present": "<yes — Metrolink/other / no / unclear>",\n'
        '    "railway_gauge": "<gauge or not visible>",\n'
        '    "language": "<languages and script>",\n'
        '    "driving_side": "<left or right or indeterminate>",\n'
        '    "ocr_text": "<ALL visible text, even partial>",\n'
        '    "sun_azimuth": "<direction or indeterminate>",\n'
        '    "hemisphere": "<north or south or indeterminate>",\n'
        '    "street_furniture": "<any notable bollards, post boxes, signage>",\n'
        '    "football_clues": "<any club colours, crests, merchandise>",\n'
        '    "waterfront_visible": "<yes / no / partial>"\n'
        '  }},\n'
        '  "heatmap_candidates": [\n'
        '    {{"lat":<float>,"lng":<float>,"weight":<0.3-1.0>}},\n'
        '    {{"lat":<float>,"lng":<float>,"weight":<0.1-0.5>}},\n'
        '    {{"lat":<float>,"lng":<float>,"weight":<0.05-0.3>}}\n'
        '  ]\n'
        '}}'
    ).format(frame_label)

    _log("Deep analysis — {}…".format(frame_label))

    models  = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    base    = ("https://generativelanguage.googleapis.com/v1beta/"
               "models/{}:generateContent")
    headers = {"Content-Type": "application/json",
               "x-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 4096},
    }

    resp = None
    for model in models:
        try:
            r = _req.post(base.format(model), json=payload,
                          headers=headers, timeout=120)
            if r.status_code == 200:
                resp = r
                _log("Model: {}".format(model))
                break
            elif r.status_code == 404:
                _log("Model {} unavailable, trying next…".format(model), "WARN")
                continue
            r.raise_for_status()
        except _req.exceptions.Timeout:
            raise RuntimeError("Timed out (120s). Try a shorter clip.")
        except _req.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response else "?"
            if code == 404:
                continue
            msg = {403: "Invalid API key or quota exceeded.",
                   429: "Rate limit — wait and retry."}.get(code, str(exc))
            raise RuntimeError("HTTP {}: {}".format(code, msg))
        except _req.exceptions.RequestException as exc:
            raise RuntimeError("Network error: {}".format(exc))

    if resp is None:
        raise RuntimeError("All Gemini models unavailable.")

    try:
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected Gemini response: {}".format(exc))

    # Robust JSON extraction with repair
    raw = re.sub(r"```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"```", "", raw).strip().strip("`").strip()
    m   = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise RuntimeError("No JSON in response:\n{}".format(raw[:400]))
    js  = m.group()
    try:
        result = json.loads(js)
    except json.JSONDecodeError:
        js2 = re.sub(r",\s*([}\]])", r"\1", js)
        try:
            result = json.loads(js2)
        except json.JSONDecodeError:
            # Last resort: strip trailing partial values and close brackets
            js3 = re.sub(r',\s*"[^"]*$', "", js2).rstrip(",")
            opens = js3.count("[") - js3.count("]")
            opens_c = js3.count("{") - js3.count("}")
            js3 += "]" * max(0, opens) + "}" * max(0, opens_c)
            try:
                result = json.loads(js3)
            except json.JSONDecodeError as exc:
                raise RuntimeError("JSON parse failed: {}".format(exc))

    _log("{} — {}%".format(
        result.get("location_name", "?"),
        result.get("confidence", "?")), "OK")
    return result
class VideoCog:
    """
    Video analysis cog.  Injected into SightPointApp by setup().

    Receives references to the running app's shared resources:
        self.root   — tk.Tk root window
        self.map    — MapWidget  (app._map)
        self.term   — TerminalConsole  (app._term)
        self.hud    — HUD  (app._hud)
        self.nb     — ttk.Notebook  (app._nb)

    The Gemini API key is read from sightpoint.GEMINI_API_KEY at
    call time so that any key entered via the Settings dialog is
    automatically picked up without restarting.
    """

    def __init__(self, app):
        self.app  = app
        self.root = app.root
        self.map  = app._map
        self.term = app._term
        self.hud  = app._hud
        self.nb   = app._nb

        # Video state
        self._video_path       = None
        self._video_frames: list = []
        self._vid_thumb_refs: list = []
        self._vid_done_count   = 0
        self._vid_total        = 0

        self._build_tab()
        self.term.log("VideoCog loaded — ▶ VIDEO tab ready.", "SYS")
        if not CV2_AVAILABLE:
            self.term.log(
                "opencv not found — install opencv-python-headless "
                "for video support.", "WARN")

    # ── Tab construction ──────────────────────────────────────
    def _build_tab(self):
        vid_tab = tk.Frame(self.nb, bg=sp.BG_DARK)
        self.nb.add(vid_tab, text="  ▶ VIDEO  ")
        self._populate_tab(vid_tab)

    def _populate_tab(self, parent):
        # ── Header bar ────────────────────────────────────────
        hdr = tk.Frame(parent, bg=sp.BG_PANEL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  VIDEO FRAME EXTRACTION & GEOLOCATION",
                  bg=sp.BG_PANEL, fg=sp.TEXT_DIM,
                  font=sp.FONT_MONO_XS).pack(side="left", pady=6)
        tk.Frame(parent, bg=sp.BORDER_LIT, height=1).pack(fill="x")

        # ── Load row ──────────────────────────────────────────
        load_row = tk.Frame(parent, bg=sp.BG_DARK)
        load_row.pack(fill="x", padx=8, pady=6)

        self._mkbtn(load_row, "◈ LOAD VIDEO",
                    self._browse_video,
                    bg=sp.CYAN, fg=sp.BG_DARK).pack(side="left", padx=(0, 10))

        self._vid_lbl = tk.Label(load_row,
                                  text="No video loaded",
                                  bg=sp.BG_DARK, fg=sp.TEXT_FAINT,
                                  font=sp.FONT_MONO_XS)
        self._vid_lbl.pack(side="left")

        # ── Options row ───────────────────────────────────────
        opt_row = tk.Frame(parent, bg=sp.BG_DARK)
        opt_row.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(opt_row, text="Max frames:",
                  bg=sp.BG_DARK, fg=sp.TEXT_DIM,
                  font=sp.FONT_MONO_XS).pack(side="left")

        self._max_frames_var = tk.IntVar(value=20)
        tk.Spinbox(opt_row,
                    textvariable=self._max_frames_var,
                    from_=2, to=60, width=4,
                    bg=sp.BG_INPUT, fg=sp.CYAN,
                    highlightthickness=0,
                    font=sp.FONT_MONO_XS).pack(side="left", padx=(4, 16))

        tk.Label(opt_row,
                  text="( duration ÷ max frames = seconds between captures )",
                  bg=sp.BG_DARK, fg=sp.TEXT_FAINT,
                  font=sp.FONT_MONO_XS).pack(side="left")

        # ── Deep analysis option row ──────────────────────────
        deep_row = tk.Frame(parent, bg=sp.BG_DARK)
        deep_row.pack(fill="x", padx=8, pady=(0, 4))

        self._deep_analysis_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            deep_row,
            text="⬡  Use deep video analysis",
            variable=self._deep_analysis_var,
            bg=sp.BG_DARK, fg=sp.CYAN,
            activebackground=sp.BG_DARK, activeforeground=sp.CYAN_BRIGHT,
            selectcolor=sp.BG_INPUT,
            font=sp.FONT_MONO_XS,
        ).pack(side="left")
        tk.Label(
            deep_row,
            text="  (richer prompt — UK city discrimination, bus liveries, "
                 "trams, football clues, calibrated confidence)",
            bg=sp.BG_DARK, fg=sp.TEXT_FAINT,
            font=sp.FONT_MONO_XS,
        ).pack(side="left")

        # ── Action buttons ────────────────────────────────────
        btn_row = tk.Frame(parent, bg=sp.BG_DARK)
        btn_row.pack(fill="x", padx=8, pady=(0, 6))

        self._mkbtn(btn_row, "▶ EXTRACT FRAMES",
                    self._extract).pack(side="left", padx=(0, 8))
        self._mkbtn(btn_row, "⬡ ANALYSE ALL  (parallel)",
                    self._analyse_all).pack(side="left", padx=(0, 8))
        self._mkbtn(btn_row, "◇ DIRECTION OF TRAVEL",
                    self._direction_of_travel).pack(side="left")

        # ── Progress label ────────────────────────────────────
        self._progress_lbl = tk.Label(parent, text="",
                                       bg=sp.BG_DARK, fg=sp.CYAN,
                                       font=sp.FONT_MONO_XS)
        self._progress_lbl.pack(anchor="w", padx=10)

        # ── Scrollable thumbnail grid ─────────────────────────
        grid_outer = tk.Frame(parent, bg=sp.BG_DARK)
        grid_outer.pack(fill="both", expand=True, padx=4, pady=4)

        grid_cv = tk.Canvas(grid_outer, bg=sp.BG_DARK, highlightthickness=0)
        grid_sb = ttk.Scrollbar(grid_outer, orient="vertical",
                                  command=grid_cv.yview)
        grid_cv.configure(yscrollcommand=grid_sb.set)
        grid_sb.pack(side="right", fill="y")
        grid_cv.pack(side="left", fill="both", expand=True)

        self._grid = tk.Frame(grid_cv, bg=sp.BG_DARK)
        wid = grid_cv.create_window((0, 0), window=self._grid, anchor="nw")
        self._grid.bind("<Configure>",
                         lambda _e: grid_cv.configure(
                             scrollregion=grid_cv.bbox("all")))
        grid_cv.bind("<Configure>",
                      lambda e: grid_cv.itemconfig(wid, width=e.width))

        # ── Bind scroll on the canvas too
        def _on_scroll(e):
            grid_cv.yview_scroll(
                -1 * (e.delta // 120 if e.delta else (-1 if e.num == 5 else 1)),
                "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            grid_cv.bind(seq, _on_scroll)

    # ── Video browse ──────────────────────────────────────────
    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="Select Video Clip",
            filetypes=[
                ("Video", "*.mp4 *.avi *.mov *.mkv *.webm *.gif"),
                ("All files", "*.*"),
            ])
        if path:
            self._load_video(path)

    def _load_video(self, path: str):
        self._video_path = path
        name = Path(path).name
        self._vid_lbl.configure(text=name, fg=sp.CYAN_BRIGHT)
        self.term.log("Video loaded: {}".format(name), "INFO")

    # ── Frame extraction ──────────────────────────────────────
    def _extract(self):
        if not self._video_path:
            messagebox.showwarning("No Video", "Load a video file first.")
            return

        self._set_progress("Extracting frames…", sp.YELLOW)
        self._clear_grid()
        self._video_frames = []
        self._vid_thumb_refs = []

        def _do():
            frames = extract_key_frames(
                self._video_path,
                max_frames=self._max_frames_var.get(),
                log_cb=lambda m, l="INFO":
                    self.root.after(0, lambda msg=m, lvl=l:
                        self.term.log(msg, lvl)))
            self.root.after(0, lambda: self._show_frames(frames))

        threading.Thread(target=_do, daemon=True).start()

    def _show_frames(self, frames: list):
        self._video_frames = frames
        if not frames:
            self._set_progress(
                "No frames extracted — check the video file and terminal.",
                sp.RED_COL)
            return

        total    = len(frames)
        interval = frames[-1]["timestamp_sec"] / total if total > 1 else 0
        self._set_progress(
            "Captured {} frames  (1 every {:.1f}s)  — "
            "click a thumbnail to load it as the main analysis image".format(
                total, interval),
            sp.GREEN)

        COLS = 5
        for i, fr in enumerate(frames):
            row, col = divmod(i, COLS)
            cell = tk.Frame(self._grid, bg=sp.BG_CARD,
                             highlightbackground=sp.BORDER,
                             highlightthickness=1)
            cell.grid(row=row, column=col, padx=4, pady=4, sticky="nw")
            cell.configure(width=165)

            # Thumbnail
            if PIL_AVAILABLE:
                try:
                    img = Image.open(fr["path"]).convert("RGB")
                    img.thumbnail((155, 88), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    self._vid_thumb_refs.append(tk_img)
                    lbl_img = tk.Label(cell, image=tk_img,
                                        bg=sp.BG_CARD, cursor="hand2")
                    lbl_img.pack()
                    lbl_img.bind(
                        "<Button-1>",
                        lambda _e, p=fr["path"]: self._load_frame_as_target(p))
                except Exception:
                    pass

            tk.Label(cell, text=fr["label"],
                      bg=sp.BG_CARD, fg=sp.CYAN,
                      font=sp.FONT_MONO_XS).pack()
            tk.Label(cell, text="frame {}".format(fr["frame_num"]),
                      bg=sp.BG_CARD, fg=sp.TEXT_FAINT,
                      font=sp.FONT_MONO_XS).pack()

            # Placeholder for result badge (filled in after analysis)
            result_lbl = tk.Label(cell, text="",
                                   bg=sp.BG_CARD, font=sp.FONT_MONO_XS,
                                   wraplength=155)
            result_lbl.pack()
            fr["_result_lbl"] = result_lbl

    def _load_frame_as_target(self, path: str):
        """Load a frame into the main app's ZoomCanvas for single-image analysis."""
        try:
            self.app._load_image(path)
            # Switch to MAP tab so the user sees the result panel
            self.nb.select(0)
            self.term.log("Frame loaded as target image.", "INFO")
        except Exception as exc:
            self.term.log("Could not load frame: {}".format(exc), "WARN")

    # ── Parallel analysis ─────────────────────────────────────
    def _analyse_all(self):
        if not self._video_frames:
            messagebox.showwarning("No Frames", "Extract frames first.")
            return

        key = sp.GEMINI_API_KEY
        if not key:
            messagebox.showerror(
                "No API Key",
                "Set your Gemini API key in Settings first.")
            return

        n = len(self._video_frames)
        self._vid_done_count = 0
        self._vid_total      = n
        mode_label = "deep" if self._deep_analysis_var.get() else "standard"
        self._set_progress(
            "Analysing {} frames in parallel  [{}]…".format(n, mode_label),
            sp.YELLOW)
        self.hud.set_status("SCANNING", sp.YELLOW)

        lock = threading.Lock()
        use_deep = self._deep_analysis_var.get()

        def _analyse_one(idx: int, fr: dict):
            """Worker thread for one frame."""
            def log_safe(msg, lvl="INFO"):
                prefix = "[frame {}] ".format(idx + 1)
                self.root.after(0, lambda m=msg, l=lvl, p=prefix:
                    self.term.log(p + m, l))
            try:
                if use_deep:
                    result = gemini_geolocate_video_frame(
                        fr["path"],
                        fr["label"],
                        sp.GEMINI_API_KEY,
                        log_cb=log_safe)
                else:
                    result = sp.gemini_geolocate(
                        fr["path"], "Global", log_cb=log_safe)
                fr["result"] = result
                self.root.after(0, lambda i=idx, r=result:
                    self._frame_result_arrived(i, r))
            except Exception as exc:
                traceback.print_exc()
                err = str(exc)
                fr["error"] = err
                self.root.after(0, lambda i=idx, e=err:
                    self._frame_result_error(i, e))

            with lock:
                self._vid_done_count += 1
                done = self._vid_done_count

            self.root.after(0, lambda d=done:
                self._update_analysis_progress(d))

        for idx, fr in enumerate(self._video_frames):
            threading.Thread(target=_analyse_one,
                              args=(idx, fr), daemon=True).start()

    def _frame_result_arrived(self, idx: int, result: dict):
        """Called on main thread when one frame finishes analysis."""
        fr   = self._video_frames[idx]
        conf = result.get("confidence", 0)
        name = result.get("location_name", "?")
        cc   = (sp.GREEN if conf >= 70
                else sp.YELLOW if conf >= 40
                else sp.RED_COL)

        # Build badge text — include deep-analysis extras if present
        osint = result.get("osint", {})
        badge_lines = ["{}\n{}%".format(name[:22], conf)]
        for key, label in [("bus_livery", "Bus"),
                            ("tram_present", "Tram"),
                            ("football_clues", "⚽")]:
            val = osint.get(key, "")
            if val and val.lower() not in ("not visible", "no", "unclear",
                                            "none", "—", ""):
                badge_lines.append("{}: {}".format(label, val[:30]))

        lbl = fr.get("_result_lbl")
        if lbl:
            try:
                lbl.configure(text="\n".join(badge_lines), fg=cc)
            except Exception:
                pass

        # Drop pin on map
        try:
            lat = float(result.get("latitude",  0))
            lng = float(result.get("longitude", 0))
            label = "{} {}%".format(fr["label"], conf)
            self.map.drop_pin(lat, lng, label)
            self.map.go_to(lat, lng, zoom=8)
        except Exception:
            pass

        self.hud.increment()
        self.term.log("Frame {} → {} ({}%)".format(
            idx + 1, name, conf), "OK")

    def _frame_result_error(self, idx: int, error: str):
        fr  = self._video_frames[idx]
        lbl = fr.get("_result_lbl")
        if lbl:
            try:
                lbl.configure(text="ERROR", fg=sp.RED_COL)
            except Exception:
                pass
        self.term.log("Frame {} failed: {}".format(idx + 1, error), "ERROR")

    def _update_analysis_progress(self, done: int):
        total = self._vid_total
        pct   = int(done / total * 100) if total else 0
        if done >= total:
            self._set_progress(
                "All {} frames analysed.".format(total), sp.GREEN)
            self.hud.set_status("COMPLETE", sp.GREEN)
        else:
            self._set_progress(
                "Analysed {}/{} frames  ({}%)…".format(done, total, pct),
                sp.YELLOW)

    # ── Direction of travel ───────────────────────────────────
    def _direction_of_travel(self):
        if len(self._video_frames) < 2:
            messagebox.showwarning(
                "Need Frames",
                "Extract at least 2 frames first.")
            return

        key = sp.GEMINI_API_KEY
        if not key:
            messagebox.showerror("No API Key",
                                  "Set your Gemini API key in Settings.")
            return

        first = self._video_frames[0]["path"]
        last  = self._video_frames[-1]["path"]

        self._set_progress("Estimating direction of travel…", sp.YELLOW)
        self.hud.set_status("SCANNING", sp.YELLOW)
        self.term.log("Direction of travel — comparing first & last frame…",
                       "INFO")

        def _do():
            try:
                result = gemini_travel_direction(
                    first, last, key,
                    log_cb=lambda m, l="INFO":
                        self.root.after(0, lambda msg=m, lvl=l:
                            self.term.log(msg, lvl)))
                self.root.after(0, lambda r=result:
                    self._show_direction_result(r))
            except Exception as exc:
                traceback.print_exc()
                err = str(exc)
                self.root.after(0, lambda e=err: (
                    self._set_progress("Direction analysis failed.", sp.RED_COL),
                    self.term.log(e, "ERROR"),
                    self.hud.set_status("ERROR", sp.RED_COL),
                ))

        threading.Thread(target=_do, daemon=True).start()

    def _show_direction_result(self, r: dict):
        self._set_progress("Direction of travel analysis complete.", sp.GREEN)
        self.hud.set_status("COMPLETE", sp.GREEN)

        top = tk.Toplevel(self.root)
        top.title("SightPoint AI — Direction of Travel")
        top.configure(bg=sp.BG_DARK)
        top.geometry("540x360")
        top.resizable(True, True)

        # Header
        hdr = tk.Frame(top, bg=sp.BG_PANEL, height=38)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="  ◇  DIRECTION OF TRAVEL",
                  bg=sp.BG_PANEL, fg=sp.CYAN,
                  font=("Courier New", 10, "bold")).pack(side="left", pady=8)
        tk.Frame(top, bg=sp.BORDER_LIT, height=1).pack(fill="x")

        body = tk.Frame(top, bg=sp.BG_DARK)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        fields = [
            ("START LOCATION",   r.get("start_location",   "—")),
            ("END LOCATION",     r.get("end_location",     "—")),
            ("DIRECTION",        r.get("direction_of_travel","—")),
            ("MOVEMENT TYPE",    r.get("movement_type",    "—")),
            ("SPEED ESTIMATE",   r.get("speed_estimate",   "—")),
            ("CONFIDENCE",       "{}%".format(r.get("confidence","—"))),
            ("REASONING",        r.get("reasoning",        "—")),
        ]

        for label, value in fields:
            row = tk.Frame(body, bg=sp.BG_CARD,
                            highlightbackground=sp.BORDER,
                            highlightthickness=1)
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text="  {}:".format(label),
                      bg=sp.BG_CARD, fg=sp.CYAN,
                      font=sp.FONT_MONO_XS,
                      width=17, anchor="w").pack(side="left",
                                                  padx=(4, 0), pady=6)
            tk.Label(row, text=str(value),
                      bg=sp.BG_CARD, fg=sp.TEXT_MID,
                      font=sp.FONT_MONO_SM,
                      wraplength=360,
                      justify="left").pack(side="left",
                                            padx=(8, 8), pady=6)

        # Route clues
        clues = r.get("route_clues", [])
        if clues:
            tk.Label(body, text="ROUTE CLUES",
                      bg=sp.BG_DARK, fg=sp.TEXT_DIM,
                      font=sp.FONT_MONO_XS).pack(anchor="w", pady=(6, 2))
            for clue in clues:
                tk.Label(body, text="  ◈  " + clue,
                          bg=sp.BG_DARK, fg=sp.TEXT_MID,
                          font=sp.FONT_MONO_SM,
                          anchor="w").pack(fill="x")

    # ── Utility helpers ───────────────────────────────────────
    def _clear_grid(self):
        for w in self._grid.winfo_children():
            try: w.destroy()
            except Exception: pass

    def _set_progress(self, text: str, colour: str = None):
        try:
            self._progress_lbl.configure(
                text=text,
                fg=colour or sp.CYAN)
        except Exception:
            pass

    def _mkbtn(self, parent, text: str, cmd,
               fg: str = sp.CYAN, bg: str = sp.BG_CARD):
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg, fg=fg,
            font=sp.FONT_MONO_XS,
            relief="flat",
            cursor="hand2",
            padx=10, pady=5,
            activebackground=sp.BORDER_LIT,
            activeforeground=sp.WHITE)


# ─────────────────────────────────────────────────────────────────
#  COG ENTRY POINT
# ─────────────────────────────────────────────────────────────────
def setup(app) -> VideoCog:
    """
    Called by main.py after SightPointApp is created.

    Returns the VideoCog instance so main.py can keep a reference
    if needed (e.g. for future hot-reload or cog management).
    """
    return VideoCog(app)
