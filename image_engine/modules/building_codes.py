"""
image_engine/modules/building_codes.py — Building Convention Analyzer
════════════════════════════════════════════════════════════════════
Architecture/construction convention analysis: roofing pitch and
material, brick bonding pattern, window/door style, foundation type
(stilts, slab, basement) — regional building conventions rather than
anything about a specific property or its occupants.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.lookup_tables import BUILDING_CONVENTIONS_DB, lookup_regions

PROMPT = (
    "Examine the building construction style in this image: roofing "
    "material and pitch, wall material (brick/stone/render/timber/"
    "stucco), window and door style, and foundation type (stilts/slab/"
    "basement).\n\n"
    "Identify which general regional building convention this matches "
    "(e.g. 'red_brick_victorian_terrace', 'clapboard_siding', "
    "'stucco_flat_roof', 'timber_frame_alpine', 'raised_stilt_house', "
    "'concrete_block_tropical') if any match clearly.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "convention_key": "<one of the keys above, or none>",\n'
    '  "construction_notes": "<what you observed>",\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "building_codes")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    conv_key = features.get("convention_key", "")
    if not features.get("detected") or not conv_key or conv_key.lower() == "none":
        result = empty_result()
        cache_set(key, result)
        return result

    regions = lookup_regions(BUILDING_CONVENTIONS_DB, conv_key)
    region_votes = {r: 0.35 for r in regions}

    result = {
        "detected": True,
        "convention_key": conv_key,
        "construction_notes": features.get("construction_notes", ""),
        "region_votes": region_votes,
        "confidence": 0.35 if region_votes else 0.15,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
