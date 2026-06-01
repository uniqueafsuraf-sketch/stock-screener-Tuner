from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

GOLD_TICKER = "GC=F"
PROXY_TICKERS = ("DX-Y.NYB", "^TNX", "UUP")  # DXY, 10Y yield, dollar ETF


@dataclass
class GoldMarketData:
    price: float
    change_pct: float
    frames: dict[str, pd.DataFrame]
    macro: dict[str, float | None]
    news: list[dict]


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.rename(columns=str.lower)
    need = {"open", "high", "low", "close", "volume"}
    if not need.issubset(out.columns):
        return None
    return out[list(need)].dropna()


def fetch_gold_data() -> GoldMarketData:
    """Pull gold OHLC across timeframes + macro proxies."""
    t = yf.Ticker(GOLD_TICKER)
    frames: dict[str, pd.DataFrame] = {}

    specs = [
        ("1M", {"period": "10y", "interval": "1mo"}),
        ("1W", {"period": "5y", "interval": "1wk"}),
        ("1D", {"period": "2y", "interval": "1d"}),
        ("4H", {"period": "60d", "interval": "1h"}),  # proxy 4H from 1h resample
        ("1H", {"period": "60d", "interval": "1h"}),
        ("15M", {"period": "5d", "interval": "15m"}),
    ]
    for label, kw in specs:
        raw = t.history(**kw, auto_adjust=True)
        df = _normalize(raw)
        if df is not None and label == "4H" and len(df) > 20:
            df = df.resample("4h").agg({
                "open": "first", "high": "max", "low": "min",
                "close": "last", "volume": "sum",
            }).dropna()
        if df is not None and len(df) >= 10:
            frames[label] = df

    price = float(frames.get("1D", frames.get("1H", pd.DataFrame())).iloc[-1]["close"]) if frames else 0.0
    chg = 0.0
    if "1D" in frames and len(frames["1D"]) > 1:
        prev = float(frames["1D"]["close"].iloc[-2])
        if prev:
            chg = ((price - prev) / prev) * 100

    macro: dict[str, float | None] = {}
    for sym, key in zip(PROXY_TICKERS, ("dxy_chg", "tnx_chg", "uup_chg")):
        try:
            h = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
            if h is not None and len(h) > 1:
                c0, c1 = float(h["Close"].iloc[-2]), float(h["Close"].iloc[-1])
                macro[key] = round(((c1 - c0) / c0) * 100, 2) if c0 else 0.0
            else:
                macro[key] = None
        except Exception:
            macro[key] = None

    news: list[dict] = []
    try:
        for item in (t.news or [])[:12]:
            news.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
            })
    except Exception:
        pass

    return GoldMarketData(price=round(price, 2), change_pct=round(chg, 2), frames=frames, macro=macro, news=news)
