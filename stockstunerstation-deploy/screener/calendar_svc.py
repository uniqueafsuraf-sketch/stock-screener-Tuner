from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import yfinance as yf


def _earnings_days(symbol: str) -> int | None:
    try:
        t = yf.Ticker(symbol)
        ed = None
        if hasattr(t, "get_earnings_dates"):
            try:
                ed = t.get_earnings_dates(limit=8)
            except Exception:
                pass
        if ed is None or (isinstance(ed, pd.DataFrame) and ed.empty):
            try:
                ed = t.earnings_dates
            except Exception:
                return None
        if ed is None or ed.empty:
            return None

        now = pd.Timestamp.now(tz="UTC")
        if ed.index.tz is None:
            idx = ed.index.tz_localize("UTC")
        else:
            idx = ed.index.tz_convert("UTC")
        future = idx[idx > now]
        if len(future) == 0:
            return None
        next_ts = future[0]
        delta = (next_ts.date() - now.date()).days
        return int(delta) if delta >= 0 else None
    except Exception:
        return None


def fetch_earnings_watch(symbols: list[str], max_workers: int = 8) -> list[dict]:
    results: list[dict] = []
    symbols = symbols[:40]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_earnings_days, s): s for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            days = fut.result()
            if days is not None and days <= 14:
                results.append({"symbol": sym, "days": days})

    results.sort(key=lambda x: x["days"])
    return results


def attach_earnings(symbols_days: dict[str, int], snapshots: list) -> None:
    for snap in snapshots:
        d = symbols_days.get(snap.symbol)
        if d is not None:
            snap.earnings_within_days = d
