#!/usr/bin/env python3
"""Sync all Ourbit tokenized stocks to data/ourbit_stocks.json."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from screener.ourbit_universe import fetch_ourbit_stocks, save_ourbit_cache


def main() -> int:
    rows = fetch_ourbit_stocks()
    path = save_ourbit_cache(rows)
    print(f"Wrote {len(rows)} Ourbit stocks -> {path}")
    for r in rows:
        print(f"  {r['ourbit_symbol']:16} -> {r['ticker']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
