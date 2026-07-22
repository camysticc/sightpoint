#!/usr/bin/env python3
"""
SightPoint AI — main.py
═══════════════════════
Entry point.  Creates the base SightPointApp from sightpoint.py
(unchanged boilerplate) then loads each cog from the cogs/ folder.

Cog protocol
────────────
Every file in cogs/ that exposes:

    def setup(app) -> CogInstance:
        ...

will be loaded automatically.  The cog receives the live
SightPointApp instance and injects itself (e.g. adds a notebook tab).

Adding a new cog
────────────────
1. Create   cogs/mycog.py
2. Implement setup(app)
3. That's it — main.py discovers and loads it automatically.

API key
───────
Stored in  ~/.sightpoint/config.json  by sightpoint.py.
Use the ⬡ SETTINGS button in the app header to set it.
"""

import argparse
import importlib
import pathlib
import tkinter as tk
from tkinter import messagebox

# ── Base application (DO NOT MODIFY) ─────────────────────────────
import sightpoint

# ─────────────────────────────────────────────────────────────────
#  COG LOADER
# ─────────────────────────────────────────────────────────────────
def _load_cogs(app) -> dict:
    """
    Scan the cogs/ directory and call setup(app) on every module
    that exposes it.  Returns { module_name: cog_instance }.
    """
    loaded = {}
    cogs_dir = pathlib.Path(__file__).parent / "cogs"

    for path in sorted(cogs_dir.glob("*.py")):
        if path.name.startswith("_"):        # skip __init__.py etc.
            continue
        mod_name = "cogs.{}".format(path.stem)
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            print("[WARN] Could not import {}: {}".format(mod_name, exc))
            continue

        if not hasattr(mod, "setup"):
            print("[INFO] {} has no setup() — skipped.".format(mod_name))
            continue

        try:
            instance = mod.setup(app)
            loaded[path.stem] = instance
            print("[INFO] Cog loaded: {}".format(mod_name))
        except Exception as exc:
            print("[ERROR] Cog setup() failed for {}: {}".format(mod_name, exc))

    return loaded


# ─────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────
def _parse_args():
    parser = argparse.ArgumentParser(
        description="SightPoint AI — Visual Geolocation Intelligence")
    parser.add_argument(
        "--options-file", metavar="PATH", default=None,
        help="Override ~/.sightpoint/options.json for this run only. "
             "See options_profiles/ for ready-made profiles "
             "(fast.json, thorough.json, ethical.json).")
    return parser.parse_args()


def main():
    args = _parse_args()

    # Load the options system before building the UI so every cog's
    # setup() sees the correct settings from the very first frame.
    import options
    if args.options_file:
        loaded = options.load_options(args.options_file)
        print("[INFO] Options loaded from override file: {}".format(
            args.options_file))
    else:
        print("[INFO] Options loaded from: {}".format(
            options.get_options_file_path()))

    root = tk.Tk()
    root.configure(bg=sightpoint.BG_DARK)

    # Dependency check
    missing = []
    if not sightpoint.REQUESTS_AVAILABLE:
        missing.append("requests          →  pip install requests")
    if not sightpoint.PIL_AVAILABLE:
        missing.append("Pillow            →  pip install pillow")
    # cv2 is optional (needed for video cog)
    try:
        import cv2  # noqa: F401
    except ImportError:
        missing.append("opencv (optional) →  pip install opencv-python-headless")

    if missing:
        messagebox.showwarning(
            "SightPoint AI — Dependencies",
            "Some packages are missing:\n\n" + "\n".join(missing) +
            "\n\nThe app will still launch; "
            "some features may be unavailable.")

    # Build base app
    app = sightpoint.SightPointApp(root)

    # Load cogs — each one injects itself into app
    cogs = _load_cogs(app)

    if not cogs:
        print("[INFO] No cogs loaded.")

    # Let the app re-attach cog tabs after a live theme reload rebuilds
    # the whole UI (see SightPointApp.reload_theme_live in sightpoint.py
    # and the Theme dialog in options/theme_dialog.py).
    app.reload_cogs_callback = lambda: _load_cogs(app)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
