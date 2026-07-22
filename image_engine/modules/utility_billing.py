"""
image_engine/modules/utility_billing.py — Utility Branding Analyzer
══════════════════════════════════════════════════════════════════
Despite the name (kept for continuity with the original module list),
this only reads visible utility-company BRANDING on vans, meters,
substations, or manhole covers — service-area logos, not billing data
or account numbers, which this never has access to and never asks for.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.lookup_tables import UTILITY_COMPANIES_DB, lookup_regions

PROMPT = (
    "Look for any visible utility company branding, logos, or markings "
    "on vehicles, meters, manhole covers, substations, or street "
    "cabinets in this image (electric, gas, water, telecoms companies).\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "companies": ["<company name>", ...],\n'
    '  "reasoning": "<what you saw and why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "utility_billing")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("companies"):
        result = empty_result()
        cache_set(key, result)
        return result

    region_votes = {}
    for company in features["companies"]:
        for region in lookup_regions(UTILITY_COMPANIES_DB, company):
            region_votes[region] = region_votes.get(region, 0) + 0.4

    result = {
        "detected": True,
        "companies": features["companies"],
        "region_votes": region_votes,
        "confidence": min(1.0, max(region_votes.values())) if region_votes else 0.2,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
