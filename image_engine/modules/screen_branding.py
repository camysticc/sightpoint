"""
image_engine/modules/screen_branding.py — On-Screen Broadcast Branding
═══════════════════════════════════════════════════════════════════════
If a TV, monitor, or digital sign is visible in the shot, its channel
bug/branding, on-screen text, or UI language/layout can narrow region —
the same idea as reading a shop sign, just on a screen instead of a
storefront.
"""

from image_engine.gemini_helper import analyze_with_gemini, empty_result
from image_engine.cache import make_image_key, cache_get, cache_set

PROMPT = (
    "Look for any television, monitor, digital signage, or screen "
    "visible in this image showing a broadcast channel logo, news "
    "ticker, on-screen UI, or branding.\n\n"
    "Return ONLY raw JSON:\n"
    '{\n'
    '  "detected": <true/false>,\n'
    '  "channel_or_brand": "<name or unknown>",\n'
    '  "likely_country": "<country or unknown>",\n'
    '  "on_screen_text": "<any readable text>",\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": "<why>"\n'
    '}'
)


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "screen_branding")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        features = analyze_with_gemini(image_path, PROMPT)
    except Exception as exc:
        result = empty_result("Gemini call failed: {}".format(exc))
        cache_set(key, result)
        return result

    if not features.get("detected") or not features.get("likely_country") or \
            features["likely_country"].lower() == "unknown":
        result = empty_result()
        cache_set(key, result)
        return result

    conf = float(features.get("confidence", 0.3))
    result = {
        "detected": True,
        "channel_or_brand": features.get("channel_or_brand", ""),
        "on_screen_text": features.get("on_screen_text", ""),
        "region_votes": {features["likely_country"]: conf},
        "confidence": conf,
        "reasoning": features.get("reasoning", ""),
    }
    cache_set(key, result)
    return result
