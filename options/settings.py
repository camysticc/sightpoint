"""
options/settings.py — SightPoint AI · Options Definitions
════════════════════════════════════════════════════════
Single source of truth for:
  • DEFAULT_OPTIONS       — every toggleable feature and its default value
  • HISTORY_CSV_HEADERS   — column order for the options-system history CSV
  • EXTRACTED_DATA_SCHEMA — JSON structure for per-image metadata files

Nothing in this file talks to disk or tkinter — it is pure data so it can
be imported safely from any cog, the core app, or a test script without
side effects.
"""

# ─────────────────────────────────────────────────────────────────
#  DEFAULT OPTIONS
#  Every key here is a dotted "category.name" string so the sidebar
#  can group them, but they are stored flat for simple get/set calls.
# ─────────────────────────────────────────────────────────────────
DEFAULT_OPTIONS = {

    # ── Data extraction ────────────────────────────────────────
    "extract_exif":            True,
    "extract_text_ocr":        True,
    "extract_vehicles":        True,
    "extract_vegetation":      True,
    "extract_weather":         True,
    "extract_time_of_day":     True,
    "extract_language":        True,
    "extract_infrastructure":  True,

    # ── Reverse search ─────────────────────────────────────────
    "reverse_search_enabled":  False,
    "reverse_search_cache":    True,

    # ── Temporal analysis ───────────────────────────────────────
    "temporal_analysis":       False,
    "detect_tampering":        False,
    "detect_image_age":        False,

    # ── Regional fingerprinting ─────────────────────────────────
    "vehicle_plates_analyzer":        True,
    "traffic_signs_analyzer":         True,
    "building_architecture_analyzer": True,
    "utility_poles_analyzer":         False,

    # ── Logging & history ────────────────────────────────────────
    "auto_save_history":       True,
    "save_extracted_data":     True,
    "save_metadata_json":      True,

    # ── Confidence tracking ──────────────────────────────────────
    "track_personal_accuracy": False,

    # ── Reporting ─────────────────────────────────────────────────
    "auto_generate_reports":         False,
    "report_format":                 "pdf",     # "pdf" or "html"
    "report_include_evidence":       True,
    "report_include_contradictions": True,

    # ── Performance ────────────────────────────────────────────────
    "cache_tiles":            True,
    "cache_reverse_search":   True,
    "cache_ocr_results":      True,
    "max_cache_size_mb":      256,

    # ── Ethical ───────────────────────────────────────────────────
    "flag_sensitive_locations":        True,
    "require_confirmation_sensitive":  True,

    # ── Deep Analysis (image_engine/ — optional forensic powerhouse) ──
    "deep_analysis_enabled":  False,
    "deep_analysis_modules": [
        "electoral_signage",
        "retail_footprint",
        "plate_forensics",
        "grid_analysis",
        "screen_branding",
        "bicycle_analysis",
        "tree_phenology",
        "utility_billing",
        "building_codes",
        "cloud_analysis",
        "sensor_analysis",
        "tower_analysis",
        "graffiti_analysis",
        "phenology_comprehensive",
        "mounting_forensics",
    ],
    "deep_analysis_cache":            True,
    "deep_analysis_timeout_seconds":  60,
}


# ─────────────────────────────────────────────────────────────────
#  HISTORY CSV HEADERS
#  Column order for ~/.sightpoint/history.csv (the options-system
#  history log — separate from sightpoint.py's own
#  ~/sightpoint_history.csv, which tracks core geolocation results).
# ─────────────────────────────────────────────────────────────────
HISTORY_CSV_HEADERS = [
    "timestamp",
    "image_path",
    "image_hash",
    "gemini_hypothesis",
    "gemini_confidence",
    "gemini_coordinates",
    "reverse_search_found",
    "reverse_search_match",
    "ocr_languages",
    "ocr_scripts",
    "vehicle_detected",
    "vehicle_region_votes",
    "temporal_flags",
    "infrastructure_region",
    "building_type",
    "weather_detected",
    "time_of_day_estimate",
    "overall_confidence",
    "contradiction_flags",
    "user_notes",
]


# ─────────────────────────────────────────────────────────────────
#  EXTRACTED DATA SCHEMA
#  Describes the JSON structure saved per-image in
#  ~/.sightpoint/metadata/<image_hash>.json
#  This is documentation-as-data — cogs are not required to fill
#  every field, only the ones relevant to what they extract.
# ─────────────────────────────────────────────────────────────────
EXTRACTED_DATA_SCHEMA = {
    "image_path":    "<str — original path to the analysed image>",
    "image_hash":    "<str — md5 hash of the image file>",
    "timestamp":     "<str — ISO 8601 timestamp of analysis>",

    "gemini": {
        "hypothesis":   "<str — location name guess>",
        "confidence":   "<int 0-100>",
        "coordinates":  {"lat": "<float>", "lng": "<float>"},
        "reasoning":    "<str>",
    },

    "exif": {
        "has_exif":  "<bool>",
        "gps":       {"latitude": "<float|null>", "longitude": "<float|null>"},
        "camera":    {"make": "<str>", "model": "<str>", "datetime": "<str>"},
    },

    "ocr": {
        "text":       "<str — all OCR'd text>",
        "languages":  ["<str>", "..."],
        "scripts":    ["<str>", "..."],
    },

    "vehicles": {
        "detected":       "<bool>",
        "types":          ["<str>", "..."],
        "region_votes":   {"<region_name>": "<int vote count>"},
        "plate_fragment": "<str|null>",
    },

    "vegetation": {
        "detected_species": ["<str>", "..."],
        "climate_zone_hint": "<str|null>",
    },

    "weather": {
        "condition":   "<str — clear/overcast/rain/snow/etc>",
        "confidence":  "<int 0-100>",
    },

    "time_of_day": {
        "estimate":       "<str — dawn/morning/midday/afternoon/dusk/night>",
        "sun_azimuth":    "<str|null>",
        "hemisphere":     "<str — north/south/indeterminate>",
    },

    "language": {
        "detected":  ["<str>", "..."],
        "scripts":   ["<str>", "..."],
    },

    "infrastructure": {
        "road_markings":   "<str|null>",
        "driving_side":    "<str — left/right/indeterminate>",
        "region_guess":     "<str|null>",
    },

    "regional_fingerprint": {
        "vehicle_plates":         "<str|null>",
        "traffic_signs":          "<str|null>",
        "building_architecture":  "<str|null>",
        "utility_poles":          "<str|null>",
    },

    "temporal": {
        "tampering_detected":  "<bool|null>",
        "estimated_age_years": "<float|null>",
        "flags":               ["<str>", "..."],
    },

    "reverse_search": {
        "performed":  "<bool>",
        "found":      "<bool>",
        "match_url":  "<str|null>",
    },

    "overall_confidence":   "<int 0-100 — combined confidence across all signals>",
    "contradiction_flags":  ["<str>", "..."],
    "user_notes":           "<str>",
}
