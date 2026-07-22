"""
image_engine/cache.py — Deep Analysis Cache
════════════════════════════════════════════
Every module result is cached by (image content hash + module name) so
re-running deep analysis on the same image doesn't re-pay the Gemini
API cost. Cache lives at ~/.sightpoint/image-engine-cache/ as one JSON
file per (image, module) pair.

Entries older than 7 days are cleaned up automatically the next time
cache_cleanup() runs (called once per app launch is enough).
"""

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".sightpoint" / "image-engine-cache"
MAX_AGE_SECONDS = 7 * 24 * 3600   # 7 days


def _cache_path(key: str) -> Path:
    # Hash the key so arbitrary strings (image paths, module names) are
    # always safe as filenames, regardless of OS path restrictions.
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / "{}.json".format(digest)


def cache_exists(key: str) -> bool:
    return _cache_path(key).exists()


def cache_get(key: str):
    """Return the cached dict for `key`, or None if missing/unreadable."""
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        return envelope.get("data")
    except (json.JSONDecodeError, OSError):
        return None


def cache_set(key: str, data) -> bool:
    """Persist `data` (must be JSON-serialisable) under `key`."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path(key)
        envelope = {"cached_at": time.time(), "key": key, "data": data}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        return True
    except (OSError, TypeError):
        return False


def cache_cleanup(max_age_seconds: int = MAX_AGE_SECONDS) -> int:
    """
    Remove cache files older than `max_age_seconds`. Returns the number
    of files removed. Safe to call on every launch — cheap no-op if
    the cache is small or empty.
    """
    removed = 0
    if not CACHE_DIR.exists():
        return removed
    now = time.time()
    for path in CACHE_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                envelope = json.load(f)
            cached_at = envelope.get("cached_at", 0)
            if now - cached_at > max_age_seconds:
                path.unlink()
                removed += 1
        except (json.JSONDecodeError, OSError):
            # Corrupt entry — remove it rather than leaving dead weight.
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def make_image_key(image_path: str, module_name: str) -> str:
    """
    Build a stable cache key from the image's actual content (not just
    its path) so a renamed/moved file still hits the cache, and an
    edited file correctly misses it.
    """
    try:
        h = hashlib.md5()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        content_hash = h.hexdigest()
    except OSError:
        content_hash = image_path   # fallback — still functional, just weaker
    return "{}::{}".format(content_hash, module_name)
