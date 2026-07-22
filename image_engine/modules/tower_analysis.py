"""
image_engine/modules/tower_analysis.py — Telecom Tower/Mast Analyzer
═══════════════════════════════════════════════════════════════════════
Cell tower/mast design (lattice vs monopole vs guyed, mounting hardware,
camouflage style) follows carrier and national standards that vary by
country — the same category of infrastructure clue as pylon design.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.lookup_tables import TOWER_STANDARDS_DB, lookup_regions

PROMPT = (
    "Look for any telecom/cell tower, mast, or antenna installation "
    "visible in this image.\n\n"
    "Describe its structure type (lattice/triangular, monopole, guyed "
    "mast, rooftop-mounted, camouflaged as a tree/pole) and any carrier "
    "branding visible.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "structure_key": "<lattice_triangular_uk/monopole_us_carrier/'
    'guyed_mast_scandinavia/concrete_pole_japan/camouflaged_tree_pole/other>",\n'
    '  "carrier_branding": "<name or none>",\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "tower_analysis")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    structure_key = features.get("structure_key", "")
    if not features.get("detected") or not structure_key or structure_key == "other":
        result = empty_result()
        cache_set(key, result)
        return result

    regions = lookup_regions(TOWER_STANDARDS_DB, structure_key)
    region_votes = {r: 0.25 for r in regions}

    result = {
        "detected": True,
        "structure_key": structure_key,
        "carrier_branding": features.get("carrier_branding", ""),
        "region_votes": region_votes,
        "confidence": 0.25 if region_votes else 0.1,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
