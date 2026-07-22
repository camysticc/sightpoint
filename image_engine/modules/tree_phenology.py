"""
image_engine/modules/tree_phenology.py — Tree Species & Seasonal State
═══════════════════════════════════════════════════════════════════════
Identifies tree/plant species with a narrow native or common cultivated
range, plus their seasonal state (bare, budding, full leaf, autumn
colour, flowering) as a secondary time-of-year signal.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.lookup_tables import TREE_SPECIES_DB, lookup_regions

PROMPT = (
    "Identify any tree or plant species visible in this image that "
    "have a distinctive, geographically narrow native or common "
    "cultivated range (e.g. palm trees, redwoods, olive trees, "
    "eucalyptus, cherry blossom). Also describe their seasonal state.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "species": ["<species name>", ...],\n'
    '  "seasonal_state": "<bare/budding/full_leaf/autumn_colour/flowering/unclear>",\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "tree_phenology")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("species"):
        result = empty_result()
        cache_set(key, result)
        return result

    region_votes = {}
    for species in features["species"]:
        for region in lookup_regions(TREE_SPECIES_DB, species):
            region_votes[region] = region_votes.get(region, 0) + 0.25

    result = {
        "detected": True,
        "species": features["species"],
        "seasonal_state": features.get("seasonal_state", "unclear"),
        "region_votes": region_votes,
        "confidence": min(1.0, max(region_votes.values())) if region_votes else 0.2,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
