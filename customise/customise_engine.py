"""
customise/customise_engine.py — SightPoint AI · Theme Engine
════════════════════════════════════════════════════════════
Loads every theme file it finds in customise/themes/*.py, applies the
active one to the running app, and persists your choice (including any
per-colour custom overrides) between launches.

Making your own theme
──────────────────────
1. Copy  customise/themes/theme_example.py  to a new file, e.g.
   customise/themes/my_theme.py
2. Change NAME and edit the THEME dict — any key you leave out falls
   back to the Cyber Dark default automatically, so you can start from
   just two or three colours and grow it later.
3. Launch (or reopen) the Theme dialog — your theme appears in the
   preset list automatically. No registration, no imports to edit.

Storage
───────
    ~/.sightpoint/theme.json    — active theme name + any custom
                                  colour/font overrides on top of it

This is a personal UI preference, kept separate from the
options_profiles/ system (which controls data-extraction toggles).
"""

import importlib.util
import json
import threading
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
#  THEMEABLE KEYS
#  Every one of these must exist as a module-level constant in
#  sightpoint.py — apply_theme_to_module() pushes values onto them.
# ─────────────────────────────────────────────────────────────────
COLOR_KEYS = [
    "BG_DARK", "BG_PANEL", "BG_CARD", "BG_INPUT",
    "BORDER", "BORDER_LIT",
    "CYAN", "CYAN_BRIGHT", "CYAN_DIM",
    "TEXT_BRIGHT", "TEXT_MID", "TEXT_DIM", "TEXT_FAINT",
    "GREEN", "YELLOW", "RED_COL", "PURPLE", "WHITE",
]

FONT_KEYS = [
    "FONT_FAMILY",          # e.g. "Courier New"
    "FONT_SIZE_NORMAL",     # base UI font size
    "FONT_SIZE_SMALL",      # secondary text size
    "FONT_SIZE_XS",         # smallest label size
]

THEME_KEYS = COLOR_KEYS + FONT_KEYS

# Human-readable labels for the theme dialog
KEY_LABELS = {
    "BG_DARK":          "Background — main",
    "BG_PANEL":         "Background — header/panels",
    "BG_CARD":          "Background — cards",
    "BG_INPUT":         "Background — input fields",
    "BORDER":           "Border — normal",
    "BORDER_LIT":       "Border — highlighted",
    "CYAN":             "Accent — primary",
    "CYAN_BRIGHT":      "Accent — bright/hover",
    "CYAN_DIM":         "Accent — dim/selection",
    "TEXT_BRIGHT":      "Text — bright (headings)",
    "TEXT_MID":         "Text — normal",
    "TEXT_DIM":         "Text — dim (labels)",
    "TEXT_FAINT":       "Text — faint (placeholders)",
    "GREEN":            "Status — success",
    "YELLOW":           "Status — warning",
    "RED_COL":          "Status — error",
    "PURPLE":           "Status — highlight",
    "WHITE":            "Text — pure white",
    "FONT_FAMILY":      "Font family",
    "FONT_SIZE_NORMAL":  "Font size — normal",
    "FONT_SIZE_SMALL":   "Font size — small",
    "FONT_SIZE_XS":       "Font size — extra small",
}

# Hardcoded fallback so the app never breaks even if the themes/
# folder is empty, missing, or every file in it fails to import.
_FALLBACK_NAME = "Cyber Dark"
_FALLBACK_THEME = {
    "BG_DARK": "#02060d", "BG_PANEL": "#050a14", "BG_CARD": "#080e1c",
    "BG_INPUT": "#0a1222", "BORDER": "#14243a", "BORDER_LIT": "#1e3d60",
    "CYAN": "#00d8ff", "CYAN_BRIGHT": "#50eaff", "CYAN_DIM": "#083040",
    "TEXT_BRIGHT": "#f4f9ff", "TEXT_MID": "#c0d4ec", "TEXT_DIM": "#5c7fa0",
    "TEXT_FAINT": "#223040", "GREEN": "#00ff99", "YELLOW": "#ffd000",
    "RED_COL": "#ff2244", "PURPLE": "#bb55ff", "WHITE": "#ffffff",
    "FONT_FAMILY": "Courier New",
    "FONT_SIZE_NORMAL": 10, "FONT_SIZE_SMALL": 8, "FONT_SIZE_XS": 7,
}

THEMES_DIR = Path(__file__).resolve().parent / "themes"

# Public alias so callers (the dialog) don't need to know about the
# leading-underscore internal name.
DEFAULT_PRESET_NAME = _FALLBACK_NAME

# ─────────────────────────────────────────────────────────────────
#  DISCOVERY — load every customise/themes/*.py file
# ─────────────────────────────────────────────────────────────────
def discover_themes() -> dict:
    """
    Scan customise/themes/*.py and import each one. A valid theme
    file defines module-level `NAME` (str) and `THEME` (dict).

    Any key missing from a theme's THEME dict is filled in from the
    Cyber Dark fallback, so a hand-written theme with only 3 colours
    still works — it just inherits the rest.

    Files that fail to import, or don't define NAME/THEME, are skipped
    with a printed warning rather than crashing the app.

    Returns { name: theme_dict }, guaranteed to contain at least
    the Cyber Dark fallback even if the folder is empty or missing.
    """
    found = {}

    try:
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
        paths = sorted(THEMES_DIR.glob("*.py"))
    except Exception:
        paths = []

    for path in paths:
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                "customise.themes.{}".format(path.stem), path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            print("[WARN] Could not load theme file {}: {}".format(path.name, exc))
            continue

        name = getattr(mod, "NAME", None)
        theme = getattr(mod, "THEME", None)
        if not name or not isinstance(theme, dict):
            print("[WARN] {} has no NAME/THEME — skipped.".format(path.name))
            continue

        merged = dict(_FALLBACK_THEME)
        merged.update(theme)
        found[name] = merged

    if _FALLBACK_NAME not in found:
        found[_FALLBACK_NAME] = dict(_FALLBACK_THEME)

    return found


# ─────────────────────────────────────────────────────────────────
#  PATHS / STATE
# ─────────────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".sightpoint"
THEME_FILE = CONFIG_DIR / "theme.json"

_THEME_LOCK = threading.RLock()
_THEME: dict = {}
_ACTIVE_PRESET_NAME = _FALLBACK_NAME
_AVAILABLE_THEMES: dict = {}   # cache of discover_themes(), refreshed on load_theme()


# ─────────────────────────────────────────────────────────────────
#  LOAD / SAVE
# ─────────────────────────────────────────────────────────────────
def load_theme() -> dict:
    """
    Refresh the list of available themes from disk, then load the
    saved active theme + any custom overrides from
    ~/.sightpoint/theme.json. Returns the merged dict and updates the
    module-level cache.
    """
    global _THEME, _ACTIVE_PRESET_NAME, _AVAILABLE_THEMES

    with _THEME_LOCK:
        _AVAILABLE_THEMES = discover_themes()

        preset_name = _FALLBACK_NAME
        merged = dict(_AVAILABLE_THEMES.get(_FALLBACK_NAME, _FALLBACK_THEME))

        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if THEME_FILE.exists():
            try:
                with open(THEME_FILE, "r", encoding="utf-8") as f:
                    on_disk = json.load(f)
                if isinstance(on_disk, dict):
                    saved_name = on_disk.get("_preset_name", preset_name)
                    # Start from the named preset if it still exists
                    # (a theme file may have been renamed/deleted since
                    # this was saved) — otherwise fall back gracefully.
                    if saved_name in _AVAILABLE_THEMES:
                        merged = dict(_AVAILABLE_THEMES[saved_name])
                    preset_name = saved_name
                    colors = on_disk.get("colors", {})
                    if isinstance(colors, dict):
                        merged.update(colors)
            except (json.JSONDecodeError, OSError):
                pass
        else:
            _write_theme_file(merged, preset_name)

        _THEME = merged
        _ACTIVE_PRESET_NAME = preset_name
        return dict(_THEME)


def _write_theme_file(theme_dict: dict, preset_name: str) -> bool:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(THEME_FILE, "w", encoding="utf-8") as f:
            json.dump({"_preset_name": preset_name, "colors": theme_dict},
                       f, indent=2)
        return True
    except OSError:
        return False


def save_theme() -> bool:
    """Persist the current in-memory theme + active preset name to disk."""
    with _THEME_LOCK:
        return _write_theme_file(_THEME, _ACTIVE_PRESET_NAME)


def get_theme_value(key: str, default=None):
    with _THEME_LOCK:
        return _THEME.get(key, default)


def set_theme_value(key: str, value) -> None:
    """Set one colour/font value and persist immediately."""
    global _ACTIVE_PRESET_NAME
    with _THEME_LOCK:
        _THEME[key] = value
        _ACTIVE_PRESET_NAME = "Custom"
        save_theme()


def get_all_theme_values() -> dict:
    with _THEME_LOCK:
        return dict(_THEME)


def get_available_themes() -> dict:
    """
    Return { name: theme_dict } for every theme file currently in
    customise/themes/. Refreshed each time load_theme() runs; call
    discover_themes() directly if you need a live re-scan mid-session
    (e.g. the Theme dialog does this so newly-added files show up
    without restarting).
    """
    with _THEME_LOCK:
        return dict(_AVAILABLE_THEMES)


def set_preset(name: str) -> dict:
    """
    Switch to a theme by name (from customise/themes/), persist
    immediately, and return the resulting theme dict. Unknown names
    are ignored.
    """
    global _THEME, _ACTIVE_PRESET_NAME
    with _THEME_LOCK:
        available = _AVAILABLE_THEMES or discover_themes()
        if name not in available:
            return dict(_THEME)
        _THEME = dict(available[name])
        _ACTIVE_PRESET_NAME = name
        save_theme()
        return dict(_THEME)


def get_active_preset_name() -> str:
    with _THEME_LOCK:
        return _ACTIVE_PRESET_NAME


def reset_to_preset_default() -> dict:
    """Reset to the Cyber Dark preset and persist immediately."""
    return set_preset(_FALLBACK_NAME)


# ─────────────────────────────────────────────────────────────────
#  APPLYING THE THEME TO sightpoint.py's MODULE CONSTANTS
# ─────────────────────────────────────────────────────────────────
def apply_theme_to_module(theme_dict: dict = None) -> None:
    """
    Push every colour value onto the `sightpoint` module's global
    constants (BG_DARK, CYAN, etc.) and rebuild its FONT_MONO* tuples
    from the font keys. Safe to call multiple times.

    Import is deferred to avoid a circular import at module load time
    (sightpoint.py doesn't import customise.customise_engine at the
    top level).
    """
    import sightpoint as sp

    theme_dict = theme_dict or get_all_theme_values()

    for key in COLOR_KEYS:
        if key in theme_dict:
            setattr(sp, key, theme_dict[key])

    family = theme_dict.get("FONT_FAMILY", "Courier New")
    size_n = int(theme_dict.get("FONT_SIZE_NORMAL", 10))
    size_s = int(theme_dict.get("FONT_SIZE_SMALL", 8))
    size_xs = int(theme_dict.get("FONT_SIZE_XS", 7))

    sp.FONT_MONO    = (family, size_n)
    sp.FONT_MONO_SM = (family, size_s)
    sp.FONT_MONO_XS = (family, size_xs)


# ─────────────────────────────────────────────────────────────────
#  AUTO-LOAD ON IMPORT
# ─────────────────────────────────────────────────────────────────
load_theme()

__all__ = [
    "COLOR_KEYS", "FONT_KEYS", "THEME_KEYS", "KEY_LABELS",
    "discover_themes", "get_available_themes", "DEFAULT_PRESET_NAME",
    "load_theme", "save_theme", "get_theme_value", "set_theme_value",
    "get_all_theme_values", "set_preset", "get_active_preset_name",
    "reset_to_preset_default", "apply_theme_to_module",
    "THEME_FILE", "CONFIG_DIR", "THEMES_DIR",
]
