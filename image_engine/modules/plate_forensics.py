"""
image_engine/modules/plate_forensics.py — Licence Plate Format Forensics
═════════════════════════════════════════════════════════════════════════
Deeper pass on licence plate FORMAT and country-of-issue only — colour
scheme, character spacing/font convention, regional code prefixes. This
is regional narrowing, the same category as the core app's existing
"license plate country" field, not an attempt to read/identify a
specific vehicle or its registered owner.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Examine any vehicle licence/number plates visible in this image. "
    "Focus ONLY on format characteristics — do NOT attempt to read a "
    "specific full registration number.\n\n"
    "Report: plate colour scheme, character format/spacing convention, "
    "any regional prefix/suffix code, and font style. Use these to "
    "identify the likely country and, if a regional code is visible, "
    "the likely sub-region.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "likely_country": "<country or unknown>",\n'
    '  "likely_subregion": "<region/state/county or unknown>",\n'
    '  "format_notes": "<colour, font, spacing observations>",\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "plate_forensics")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("likely_country") or \
            features["likely_country"].lower() == "unknown":
        result = empty_result()
        cache_set(key, result)
        return result

    conf = float(features.get("confidence", 0.4))
    region_votes = {features["likely_country"]: conf}
    if features.get("likely_subregion") and features["likely_subregion"].lower() != "unknown":
        region_votes[features["likely_subregion"]] = conf * 0.8

    result = {
        "detected": True,
        "likely_country": features["likely_country"],
        "likely_subregion": features.get("likely_subregion", ""),
        "format_notes": features.get("format_notes", ""),
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
