#!/usr/bin/env python3
"""Refresh data/congress_trades.json from public STOCK Act sources."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from screener.congress_trades import build_congress_payload, save_congress_cache  # noqa: E402


def main() -> int:
    payload = build_congress_payload(lookback_days=180)
    if not payload.get("ok"):
        print("Failed:", payload.get("error"))
        return 1
    save_congress_cache(payload)
    stats = payload.get("stats") or {}
    print(
        f"Congress trades: {payload.get('total_trades')} total, "
        f"{stats.get('recent_buy_count', 0)} recent buys, "
        f"{stats.get('symbols_with_buys', 0)} symbols with buys"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
