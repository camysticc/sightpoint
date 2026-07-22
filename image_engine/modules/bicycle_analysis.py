"""
image_engine/modules/bicycle_analysis.py — Cycling Infrastructure Analyzer
═══════════════════════════════════════════════════════════════════════════
Bike-share scheme branding, cycle lane paint conventions, and bicycle
style/type all vary regionally — the same category of infrastructure
clue as road markings or traffic signal design.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Look for bicycles, bike-share docking stations, cycle lane "
    "markings, or cycling infrastructure in this image.\n\n"
    "Note any bike-share scheme branding/colours, cycle lane paint "
    "style (colour, symbol conventions), and bicycle types that hint "
    "at a specific city or country.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "bikeshare_brand": "<name or none>",\n'
    '  "lane_style_notes": "<description>",\n'
    '  "likely_regions": ["<region1>", "<region2>"],\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "bicycle_analysis")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("likely_regions"):
        result = empty_result()
        cache_set(key, result)
        return result

    conf = float(features.get("confidence", 0.25))
    region_votes = {r: conf for r in features["likely_regions"]}

    result = {
        "detected": True,
        "bikeshare_brand": features.get("bikeshare_brand", ""),
        "lane_style_notes": features.get("lane_style_notes", ""),
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
