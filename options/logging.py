"""
options/logging.py — SightPoint AI · Options-System CSV History
═════════════════════════════════════════════════════════════════
Manages ~/.sightpoint/history.csv — a broader history log than
sightpoint.py's own ~/sightpoint_history.csv. This one is designed to
be populated by any cog that extracts additional signal (vehicles,
OCR languages, temporal flags, reverse-search hits, etc.) so that
data lives alongside the core geolocation result rather than being
lost after the analysis panel closes.

This module never imports tkinter and never raises on I/O failure —
a logging problem should never crash an analysis.
"""

import csv
import threading
from pathlib import Path

from options.settings import HISTORY_CSV_HEADERS

_CSV_LOCK = threading.RLock()


def _csv_path() -> Path:
    """Resolve the history CSV path (imported lazily to avoid circular import)."""
    from pathlib import Path as _P
    return _P.home() / ".sightpoint" / "history.csv"


def ensure_history_csv() -> None:
    """
    Create ~/.sightpoint/history.csv with the correct header row if it
    doesn't already exist. Safe to call on every launch.
    """
    path = _csv_path()
    with _CSV_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.stat().st_size == 0:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=HISTORY_CSV_HEADERS).writeheader()
        except OSError:
            pass


def append_history(row_dict: dict) -> bool:
    """
    Append a single analysis row to the history CSV without rewriting
    the whole file. Missing columns are left blank; unknown extra
    keys in `row_dict` are silently ignored (DictWriter with
    extrasaction="ignore") so cogs don't need to know every column.

    Returns True on success, False on failure (never raises).
    """
    path = _csv_path()
    with _CSV_LOCK:
        try:
            ensure_history_csv()
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=HISTORY_CSV_HEADERS, extrasaction="ignore")
                writer.writerow(row_dict)
            return True
        except OSError:
            return False


def get_history() -> list:
    """
    Read the entire history CSV and return it as a list of dicts
    (one dict per row, using HISTORY_CSV_HEADERS as keys).
    Returns an empty list if the file doesn't exist or can't be read.
    """
    path = _csv_path()
    with _CSV_LOCK:
        if not path.exists():
            return []
        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except OSError:
            return []
