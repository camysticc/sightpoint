"""
options — SightPoint AI · Options / Settings System
════════════════════════════════════════════════════
Thread-safe, disk-persisted, fine-grained control over what every cog
extracts, logs, and reports.

File locations
──────────────
    options_profiles/default.json       — active settings profile
                                           (created on first launch,
                                           written to immediately on
                                           every sidebar/dialog change)
    ~/.sightpoint/history.csv           — options-system history log
    ~/.sightpoint/metadata/<hash>.json  — per-image extracted-data JSON

Any changes made in the Settings sidebar or the Options dialog are
written straight into whichever profile is currently active inside
options_profiles/ — there is no separate "save" step.

Quick start (from any cog)
───────────────────────────
    import options

    if options.get_option("extract_vehicles"):
        vehicles = analyze_vehicles(image_path)

    if options.get_option("auto_save_history"):
        options.append_history({
            "timestamp":          datetime.now().isoformat(),
            "image_path":         image_path,
            "vehicle_detected":   vehicle_name,
            # ... any subset of options.settings.HISTORY_CSV_HEADERS
        })

Toggling a setting from UI code (already wired up by SettingsSidebar,
but you can call this directly too):

    options.set_option("extract_vehicles", False)
    options.toggle_option("reverse_search_enabled")

Every set_option() / toggle_option() call writes the active profile
JSON in options_profiles/ immediately — there is no "save" step to
remember, and no batching that could lose changes if the app crashes.

Switching profiles for a single run
────────────────────────────────────
    python main.py --options-file options_profiles/thorough.json

See options_profiles/ for ready-made profiles (fast.json, thorough.json,
ethical.json, default.json) you can copy, edit, and pass with
--options-file, or select from the Theme/Options dialogs in the UI.
"""

import json
import threading
from pathlib import Path

from options.settings import DEFAULT_OPTIONS, HISTORY_CSV_HEADERS, EXTRACTED_DATA_SCHEMA
from options.logging import (
    ensure_history_csv,
    append_history,
    get_history,
)
from options.metadata import (
    save_image_metadata,
    load_image_metadata,
    export_all_metadata_csv,
)

# ─────────────────────────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────────────────────────
# Project root = the folder containing main.py / sightpoint.py / options/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROFILES_DIR = _PROJECT_ROOT / "options_profiles"
OPTIONS_FILE = PROFILES_DIR / "default.json"   # active profile by default

# History/metadata are personal runtime data, not a portable "profile" —
# these stay in the user's home directory as before.
CONFIG_DIR   = Path.home() / ".sightpoint"
HISTORY_CSV  = CONFIG_DIR / "history.csv"
METADATA_DIR = CONFIG_DIR / "metadata"

# ─────────────────────────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────────────────────────
_OPTIONS_LOCK = threading.RLock()
_OPTIONS: dict = {}
_ACTIVE_OPTIONS_FILE = OPTIONS_FILE   # may be overridden by --options-file


# ─────────────────────────────────────────────────────────────────
#  LOAD / SAVE
# ─────────────────────────────────────────────────────────────────
def load_options(path: str = None) -> dict:
    """
    Load options from disk, falling back to DEFAULT_OPTIONS for any
    missing keys (so upgrading the app with new options never crashes
    on an old profile file).

    If `path` is given, that file becomes the active profile for this
    session (used by --options-file, or by picking a different profile
    from the UI). Otherwise options_profiles/default.json is used.

    Returns the merged options dict. Also updates the module-level
    _OPTIONS cache used by get_option()/set_option().
    """
    global _OPTIONS, _ACTIVE_OPTIONS_FILE

    with _OPTIONS_LOCK:
        target = Path(path) if path else OPTIONS_FILE
        _ACTIVE_OPTIONS_FILE = target

        merged = dict(DEFAULT_OPTIONS)   # start from defaults

        try:
            PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    on_disk = json.load(f)
                if isinstance(on_disk, dict):
                    merged.update(on_disk)
            except (json.JSONDecodeError, OSError):
                # Corrupt or unreadable file — fall back to defaults,
                # but don't crash the app over a bad settings file.
                pass
        else:
            # First launch — write defaults so the file exists and is
            # inspectable/editable by the user immediately.
            try:
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(merged, f, indent=2)
            except OSError:
                pass

        _OPTIONS = merged
        return dict(_OPTIONS)


def save_options() -> bool:
    """
    Write the current in-memory options to the active profile file
    (inside options_profiles/, or wherever --options-file pointed).
    Returns True on success, False on failure (never raises — a failed
    save should not crash the app; it's logged by the caller instead).
    """
    with _OPTIONS_LOCK:
        try:
            _ACTIVE_OPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_ACTIVE_OPTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(_OPTIONS, f, indent=2)
            return True
        except OSError:
            return False


def list_profiles() -> list:
    """
    Return the names (without .json) of every profile file currently
    sitting in options_profiles/, sorted alphabetically. Used by the
    Options dialog's profile switcher.
    """
    try:
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))
    except Exception:
        return []


def get_active_profile_name() -> str:
    """Return the stem (no .json) of the currently active profile file."""
    return Path(_ACTIVE_OPTIONS_FILE).stem


def get_option(key: str, default=None):
    """
    Retrieve a setting. Falls back to `default` if the key is missing
    entirely (should be rare since load_options() merges with
    DEFAULT_OPTIONS, but this keeps get_option() safe to call even
    before load_options() has run).
    """
    with _OPTIONS_LOCK:
        if key in _OPTIONS:
            return _OPTIONS[key]
        if key in DEFAULT_OPTIONS:
            return DEFAULT_OPTIONS[key]
        return default


def set_option(key: str, value) -> None:
    """
    Set a setting and persist it to disk immediately.
    Thread-safe — safe to call from any cog's background thread.
    """
    with _OPTIONS_LOCK:
        _OPTIONS[key] = value
        save_options()


def toggle_option(key: str) -> bool:
    """
    Flip a boolean option and persist immediately.
    Returns the new value. If the key doesn't currently hold a bool,
    it is coerced with `not bool(current_value)`.
    """
    with _OPTIONS_LOCK:
        current = get_option(key, False)
        new_value = not bool(current)
        set_option(key, new_value)
        return new_value


def get_all_options() -> dict:
    """Return a shallow copy of every current option (for the sidebar UI)."""
    with _OPTIONS_LOCK:
        return dict(_OPTIONS)


def reset_to_defaults() -> dict:
    """
    Reset every option back to DEFAULT_OPTIONS and persist immediately.
    Returns the resulting options dict.
    """
    global _OPTIONS
    with _OPTIONS_LOCK:
        _OPTIONS = dict(DEFAULT_OPTIONS)
        save_options()
        return dict(_OPTIONS)


def get_options_file_path() -> str:
    """Return the path of the currently active options file, as a string."""
    return str(_ACTIVE_OPTIONS_FILE)


# ─────────────────────────────────────────────────────────────────
#  AUTO-LOAD ON IMPORT
#  Every module that does `import options` gets settings ready
#  immediately with zero setup required.
# ─────────────────────────────────────────────────────────────────
load_options()
ensure_history_csv()

__all__ = [
    "load_options", "save_options", "get_option", "set_option",
    "toggle_option", "get_all_options", "reset_to_defaults",
    "get_options_file_path", "list_profiles", "get_active_profile_name",
    "ensure_history_csv", "append_history", "get_history",
    "save_image_metadata", "load_image_metadata", "export_all_metadata_csv",
    "DEFAULT_OPTIONS", "HISTORY_CSV_HEADERS", "EXTRACTED_DATA_SCHEMA",
    "CONFIG_DIR", "OPTIONS_FILE", "PROFILES_DIR", "HISTORY_CSV", "METADATA_DIR",
]
