"""
image_engine/modules/cloud_analysis.py — Cloud & Weather Pattern Analyzer
══════════════════════════════════════════════════════════════════════════
Cloud type, sky colour/haze, and visible precipitation give secondary
hemisphere/season/climate-zone signals — complements the main app's
existing sun-azimuth/shadow analysis with a sky-focused pass.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Analyse the sky and weather conditions visible in this image: "
    "cloud type (cumulus, stratus, cirrus, storm clouds, clear), "
    "haze/pollution level, apparent humidity, and any precipitation.\n\n"
    "Estimate the likely climate zone this is consistent with (e.g. "
    "tropical, temperate, arid, polar, monsoon) and note if the light "
    "quality suggests a specific season.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "cloud_type": "<description>",\n'
    '  "likely_climate_zones": ["<zone1>", "<zone2>"],\n'
    '  "season_hint": "<description or unclear>",\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "cloud_analysis")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("likely_climate_zones"):
        result = empty_result()
        cache_set(key, result)
        return result

    conf = float(features.get("confidence", 0.2))
    region_votes = {z: conf for z in features["likely_climate_zones"]}

    result = {
        "detected": True,
        "cloud_type": features.get("cloud_type", ""),
        "season_hint": features.get("season_hint", "unclear"),
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
