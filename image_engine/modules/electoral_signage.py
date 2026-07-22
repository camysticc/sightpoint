"""
image_engine/modules/electoral_signage.py — Electoral Signage Analyzer
════════════════════════════════════════════════════════════════════
Reads visible campaign posters, party logos, and election signage.
Political parties on public display at a public election are exactly
that — public — so this only maps party *names* to the regions they
contest, never anything about individual private citizens.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.lookup_tables import ELECTORAL_PARTIES_DB, lookup_regions

PROMPT = (
    "Look for any political campaign posters, party logos, election "
    "signage, or ballot advertising visible in this image.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "parties_or_candidates": ["<party or candidate name>", ...],\n'
    '  "election_type": "<local/national/regional/unknown>",\n'
    '  "reasoning": "<what you saw and why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "electoral_signage")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("parties_or_candidates"):
        result = empty_result()
        cache_set(key, result)
        return result

    region_votes = {}
    for name in features["parties_or_candidates"]:
        for region in lookup_regions(ELECTORAL_PARTIES_DB, name):
            region_votes[region] = region_votes.get(region, 0) + 0.3

    result = {
        "detected": True,
        "parties_or_candidates": features["parties_or_candidates"],
        "election_type": features.get("election_type", "unknown"),
        "region_votes": region_votes,
        "confidence": min(1.0, max(region_votes.values())) if region_votes else 0.2,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
