"""
image_engine/modules/mounting_forensics.py — Sign/Fixture Mounting Hardware
════════════════════════════════════════════════════════════════════════════
Mounting hardware conventions for road signs, street lights, and
security cameras (bracket type, pole material, height/angle standard)
vary by country's infrastructure code — a subtle but real regional
signal, in the same family as the road-sign-typography check the core
app's main prompt already does.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Examine how any signs, street lights, or cameras in this image "
    "are mounted: bracket/clamp style, pole material (steel/concrete/"
    "wood), mounting height convention, and angle.\n\n"
    "Note anything distinctive about the mounting hardware that "
    "suggests a specific country's infrastructure standard.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "mounting_notes": "<description>",\n'
    '  "likely_regions": ["<region1>", "<region2>"],\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "mounting_forensics")
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

    conf = float(features.get("confidence", 0.15))
    region_votes = {r: conf for r in features["likely_regions"]}

    result = {
        "detected": True,
        "mounting_notes": features.get("mounting_notes", ""),
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
