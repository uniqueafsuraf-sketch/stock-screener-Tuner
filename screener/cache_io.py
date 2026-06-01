from __future__ import annotations

import json
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "scan_cache.json"
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_bootstrap.json"


def load_scan_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if data.get("all_stocks"):
            return data
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return None


def load_seed_bootstrap() -> dict | None:
    """Bundled scan data for cloud deploy (Render cold start)."""
    if not SEED_PATH.exists():
        return None
    try:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        if data.get("all_stocks"):
            return data
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return None


def save_scan_cache(payload: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, indent=0), encoding="utf-8")
    except OSError:
        pass
