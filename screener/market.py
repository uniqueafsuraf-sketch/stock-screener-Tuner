from __future__ import annotations

import time

from screener.live import fetch_live_quotes
from screener.market_symbols import MARKET_SYMBOLS, MARKET_TICKERS


def fetch_market_pulse() -> list[dict]:
    quotes = fetch_live_quotes(MARKET_SYMBOLS)

    pulse = []
    for sym, label in MARKET_TICKERS:
        q = quotes.get(sym)
        if not q:
            continue
        pulse.append({
            "symbol": sym,
            "label": label,
            "price": q.price,
            "change_pct": q.change_pct,
            "volume_ratio": q.volume_ratio,
            "updated_at": time.time(),
        })

    return pulse
