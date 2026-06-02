#!/usr/bin/env python3
"""Refresh Ourbit pair list from API and copy to dashboard/static."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from screener.ourbit_universe import CACHE_PATH, STATIC_CACHE_PATH, fetch_ourbit_stocks, save_ourbit_cache  # noqa: E402


def main() -> int:
    rows = fetch_ourbit_stocks()
    save_ourbit_cache(rows)
    shutil.copy2(CACHE_PATH, STATIC_CACHE_PATH)
    print(f"Ourbit pairs: {len(rows)}")
    print(f"Wrote {CACHE_PATH}")
    print(f"Copied to {STATIC_CACHE_PATH}")
    tickers = [r["ticker"] for r in rows]
    print("Tickers:", ", ".join(tickers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
