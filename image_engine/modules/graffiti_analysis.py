"""
image_engine/modules/graffiti_analysis.py — Street Art Regional Style
════════════════════════════════════════════════════════════════════
NARROWED FROM THE ORIGINAL SPEC — see image_engine/__init__.py.

The original plan cross-referenced tag style against a "known artist"
database to identify who made a specific piece. Most graffiti artists
are deliberately anonymous — often specifically to avoid prosecution
for vandalism — so a name-matching tool here would be a targeted
deanonymisation capability aimed at people who have real legal and
safety reasons to stay unidentified.

What this module actually does is describe the general STYLE of any
street art/graffiti visible (tagging convention, colour palette,
stencil vs freehand, characteristic lettering styles associated with
specific street art scenes) purely as a "this style is common in city
X's street art scene" regional signal — never a lookup against a
specific named individual.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "If any graffiti, street art, or tagging is visible in this image, "
    "describe its general STYLE only: lettering convention, colour "
    "palette, stencil vs freehand technique, and whether the style is "
    "characteristic of a well-known street art scene/movement (e.g. "
    "'East London style', 'Berlin wall-art tradition', 'São Paulo "
    "pixação').\n\n"
    "Do NOT attempt to identify a specific artist — describe the style "
    "category only.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "style_description": "<general style notes>",\n'
    '  "associated_scenes": ["<city/region street art scene>", ...],\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "graffiti_analysis")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("associated_scenes"):
        result = empty_result()
        cache_set(key, result)
        return result

    conf = float(features.get("confidence", 0.15))
    region_votes = {scene: conf for scene in features["associated_scenes"]}

    result = {
        "detected": True,
        "style_description": features.get("style_description", ""),
        "region_votes": region_votes,
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
