"""
image_engine/modules/grid_analysis.py — Power Grid / Pylon Design Analyzer
═══════════════════════════════════════════════════════════════════════════
Electrical infrastructure design (pylon/pole shape, transformer box
style, overhead vs underground convention, voltage-class insulator
type) varies strongly by country and utility standard — a solid
regional signal, same category as street furniture or road markings.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Examine any electrical infrastructure visible in this image: "
    "pylons, utility poles, transformer boxes, overhead lines, "
    "insulators.\n\n"
    "Describe the pole/pylon material and design (wooden pole vs steel "
    "lattice vs concrete), whether lines are overhead or underground, "
    "and any distinctive regional convention this suggests.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "pole_type": "<wooden/steel_lattice/concrete/none_visible>",\n'
    '  "line_convention": "<overhead/underground/unknown>",\n'
    '  "likely_regions": ["<region1>", "<region2>"],\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "grid_analysis")
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

    conf = float(features.get("confidence", 0.3))
    region_votes = {r: conf for r in features["likely_regions"]}

    result = {
        "detected": True,
        "pole_type": features.get("pole_type", "unknown"),
        "line_convention": features.get("line_convention", "unknown"),
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
