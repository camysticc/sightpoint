"""
image_engine/modules/retail_footprint.py — Retail Chain Footprint
══════════════════════════════════════════════════════════════════
Identifies visible retail/supermarket/pharmacy chain branding and
cross-references against which countries each chain actually operates
in — a strong regional narrowing signal since most chains are highly
geographically concentrated.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.lookup_tables import RETAIL_CHAINS_DB, lookup_regions

PROMPT = (
    "Identify any retail store, supermarket, pharmacy, or restaurant "
    "chain branding, logos, or shopfronts visible in this image.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "chains": ["<chain name>", ...],\n'
    '  "reasoning": "<what you saw and why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "retail_footprint")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("chains"):
        result = empty_result()
        cache_set(key, result)
        return result

    region_votes = {}
    for chain in features["chains"]:
        for region in lookup_regions(RETAIL_CHAINS_DB, chain):
            region_votes[region] = region_votes.get(region, 0) + 0.35

    result = {
        "detected": True,
        "chains": features["chains"],
        "region_votes": region_votes,
        "confidence": min(1.0, max(region_votes.values())) if region_votes else 0.2,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
