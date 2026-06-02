#!/usr/bin/env python3
"""Rebuild data/seed_bootstrap.json from data/scan_cache.json (full stocks + ETFs)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CACHE = ROOT / "data" / "scan_cache.json"
SEED = ROOT / "data" / "seed_bootstrap.json"
STATIC_SEED = ROOT / "dashboard" / "static" / "seed_bootstrap.json"


def _slim_row(row: dict) -> dict:
    out = dict(row)
    out.pop("live", None)
    news = out.get("news") or []
    out["news"] = [
        {
            "title": n.get("title", ""),
            "url": n.get("url", ""),
            "published": n.get("published", ""),
            "sentiment": n.get("sentiment", ""),
        }
        for n in news[:3]
    ]
    return out


def main() -> int:
    if not CACHE.exists():
        print("Run a local scan first (START.bat) to create data/scan_cache.json")
        return 1

    src = json.loads(CACHE.read_text(encoding="utf-8"))
    stocks = [_slim_row(s) for s in (src.get("all_stocks") or [])]
    if not stocks:
        print("scan_cache.json has no all_stocks")
        return 1

    out = dict(src)
    for key in (
        "opportunities", "all_stocks", "edge_plays", "gainers", "losers",
        "gaps", "high_rvol", "rel_strength", "unusual_activity",
    ):
        if key in out and isinstance(out[key], list):
            out[key] = [_slim_row(s) if isinstance(s, dict) else s for s in out[key]]

    out["all_stocks"] = stocks
    out["symbols_scanned"] = len(stocks)
    out["universe_size"] = len(stocks)
    out["message"] = "Full universe loaded — live quotes updating…"
    out.pop("live", None)

    from dashboard.server import _apply_ourbit_payload  # noqa: PLC0415

    out = _apply_ourbit_payload(out)
    if isinstance(out.get("news_wire"), list) and len(out["news_wire"]) > 150:
        out["news_wire"] = out["news_wire"][:150]

    payload = json.dumps(out, separators=(",", ":"))
    SEED.write_text(payload, encoding="utf-8")
    STATIC_SEED.write_text(payload, encoding="utf-8")
    print(
        f"Wrote {SEED} and {STATIC_SEED} — {len(stocks)} symbols, {SEED.stat().st_size:,} bytes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
