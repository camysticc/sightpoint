"""
options/metadata.py — SightPoint AI · Per-Image Metadata Store
════════════════════════════════════════════════════════════════
Saves the full extracted-data JSON (see settings.EXTRACTED_DATA_SCHEMA)
for each analysed image to ~/.sightpoint/metadata/<image_hash>.json.

Keyed by image hash (not filename) so the same image analysed twice
from different paths/names still resolves to the same metadata record,
and so metadata survives the source file being moved or renamed.
"""

import json
import csv
import hashlib
import threading
from pathlib import Path

_METADATA_LOCK = threading.RLock()


def _metadata_dir() -> Path:
    d = Path.home() / ".sightpoint" / "metadata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hash_image(image_path: str) -> str:
    """MD5 hash of the image file contents. Used as the storage key."""
    h = hashlib.md5()
    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_image_metadata(image_path: str, extracted_data_dict: dict) -> str:
    """
    Save `extracted_data_dict` as JSON to
    ~/.sightpoint/metadata/<image_hash>.json

    The image_path and image_hash are injected into the saved JSON
    automatically if not already present, so callers don't need to
    duplicate that bookkeeping.

    Returns the path to the saved JSON file as a string.
    Returns "" if the image couldn't be read/hashed or the file
    couldn't be written (never raises).
    """
    with _METADATA_LOCK:
        try:
            img_hash = _hash_image(image_path)
        except (OSError, FileNotFoundError):
            return ""

        data = dict(extracted_data_dict)
        data.setdefault("image_path", image_path)
        data.setdefault("image_hash", img_hash)

        out_path = _metadata_dir() / "{}.json".format(img_hash)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return str(out_path)
        except OSError:
            return ""


def load_image_metadata(image_path: str) -> dict:
    """
    Retrieve previously saved metadata for an image, keyed by its
    content hash. Returns {} if no metadata has been saved for this
    image, or if the image/JSON can't be read.
    """
    with _METADATA_LOCK:
        try:
            img_hash = _hash_image(image_path)
        except (OSError, FileNotFoundError):
            return {}

        in_path = _metadata_dir() / "{}.json".format(img_hash)
        if not in_path.exists():
            return {}
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}


def load_metadata_by_hash(image_hash: str) -> dict:
    """Same as load_image_metadata() but when you already have the hash."""
    with _METADATA_LOCK:
        in_path = _metadata_dir() / "{}.json".format(image_hash)
        if not in_path.exists():
            return {}
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}


def list_all_metadata() -> list:
    """Return a list of all saved metadata dicts (one per JSON file)."""
    with _METADATA_LOCK:
        results = []
        for p in sorted(_metadata_dir().glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                continue
        return results


def _flatten(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dict into dotted-key form for CSV export."""
    items = {}
    for k, v in d.items():
        new_key = "{}{}{}".format(parent_key, sep, k) if parent_key else k
        if isinstance(v, dict):
            items.update(_flatten(v, new_key, sep=sep))
        elif isinstance(v, list):
            items[new_key] = "; ".join(str(x) for x in v)
        else:
            items[new_key] = v
    return items


def export_all_metadata_csv(output_path: str) -> bool:
    """
    Flatten every saved per-image metadata JSON into a single CSV file
    at `output_path`. Nested dict keys become dotted column names
    (e.g. "gemini.confidence"); lists are joined with "; ".

    Column set is the union of all keys seen across every metadata
    file, so this works even if different cogs have saved different
    subsets of the schema for different images.

    Returns True on success, False on failure (never raises).
    """
    with _METADATA_LOCK:
        records = list_all_metadata()
        if not records:
            return False

        flattened = [_flatten(r) for r in records]

        all_keys = []
        seen = set()
        for row in flattened:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)

        try:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
                writer.writeheader()
                for row in flattened:
                    writer.writerow(row)
            return True
        except OSError:
            return False
