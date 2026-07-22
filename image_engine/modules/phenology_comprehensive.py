"""
image_engine/modules/phenology_comprehensive.py — Comprehensive Seasonal Analyzer
════════════════════════════════════════════════════════════════════════════════
Broader companion to tree_phenology.py — looks at ALL visible plant
life together (grass condition, flowering state, leaf coverage across
multiple species, agricultural crop stage if any) to triangulate season
and, secondarily, hemisphere — complements the single-species-focused
tree_phenology module with a whole-scene read.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Examine ALL visible vegetation in this image together — grass "
    "condition, general leaf coverage across all visible plants and "
    "trees, flowering state, and any agricultural crops and their "
    "growth stage.\n\n"
    "Synthesise these into a single best estimate of season and, if "
    "possible, hemisphere (vegetation patterns reverse between "
    "northern and southern hemisphere).\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "season_estimate": "<spring/summer/autumn/winter/unclear>",\n'
    '  "hemisphere_estimate": "<northern/southern/unclear>",\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "phenology_comprehensive")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    season = features.get("season_estimate", "unclear")
    hemisphere = features.get("hemisphere_estimate", "unclear")
    if not features.get("detected") or (season == "unclear" and hemisphere == "unclear"):
        result = empty_result()
        cache_set(key, result)
        return result

    conf = float(features.get("confidence", 0.2))
    region_votes = {}
    if hemisphere != "unclear":
        region_votes[hemisphere.capitalize() + " Hemisphere"] = conf

    result = {
        "detected": True,
        "season_estimate": season,
        "hemisphere_estimate": hemisphere,
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
