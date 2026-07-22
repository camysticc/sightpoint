"""
image_engine/modules/sensor_analysis.py — Camera Metadata Analyzer
════════════════════════════════════════════════════════════════════
NARROWED FROM THE ORIGINAL SPEC — see image_engine/__init__.py.

The original plan for this module was "camera sensor fingerprinting":
matching sensor noise patterns (PRNU) to identify a specific physical
camera and link supposedly-unrelated photos back to the same device.
That's a real, documented deanonymisation technique used against
photographers, journalists, and activists who rely on their photos not
being linkable to each other or to them — so it isn't built here.

What this module actually does is read the image's own EXIF camera
make/model/software tags — the same metadata the core app already
surfaces in its EXIF panel — and use it only as a weak corroborating
signal (e.g. "this camera model was predominantly sold in region X"),
never to link this photo to any other photo.
"""

from PIL import Image, ExifTags

from image_engine.cache import make_image_key, cache_get, cache_set
from image_engine.gemini_helper import empty_result

# Camera brands with a historically strong regional sales concentration.
# Weak signal only — deliberately not treated as a strong vote.
_BRAND_REGION_HINTS = {
    "fujifilm": ["Japan"],
    "ricoh": ["Japan"],
    "olympus": ["Japan"],
}


def analyze(image_path: str, geolocation_result: dict) -> dict:
    key = make_image_key(image_path, "sensor_analysis")
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        img = Image.open(image_path)
        exif_raw = img._getexif() if hasattr(img, "_getexif") else None
    except Exception as exc:
        result = empty_result("Could not read EXIF: {}".format(exc))
        cache_set(key, result)
        return result

    if not exif_raw:
        result = empty_result("No EXIF camera metadata present.")
        cache_set(key, result)
        return result

    named = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif_raw.items()}
    make = str(named.get("Make", "")).strip()
    model = str(named.get("Model", "")).strip()

    if not make and not model:
        result = empty_result("No camera make/model in EXIF.")
        cache_set(key, result)
        return result

    region_votes = {}
    for brand, regions in _BRAND_REGION_HINTS.items():
        if brand in make.lower():
            for region in regions:
                region_votes[region] = 0.1   # deliberately weak — brand
                                              # sales region is a very
                                              # soft signal, not proof

    result = {
        "detected": True,
        "camera_make": make,
        "camera_model": model,
        "region_votes": region_votes,
        "confidence": 0.1 if region_votes else 0.0,
        "reasoning": "EXIF camera metadata read: {} {}. "
                     "(No sensor-fingerprint matching is performed.)".format(
                         make, model),
    }
    cache_set(key, result)
    return result
