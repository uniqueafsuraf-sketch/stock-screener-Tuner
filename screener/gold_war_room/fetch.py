from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

GOLD_TICKERS = ("GC=F", "GLD", "XAUUSD=X")
PROXY_TICKERS = ("UUP", "^TNX", "DX-Y.NYB")

_CACHE: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 60


@dataclass
class GoldMarketData:
    price: float
    change_pct: float
    frames: dict[str, pd.DataFrame]
    macro: dict[str, float | None]
    news: list[dict]
    data_source: str = "live"
    fetch_notes: list[str] = field(default_factory=list)


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.droplevel(0, axis=1)
        except Exception:
            df.columns = [str(c[-1] if isinstance(c, tuple) else c).lower() for c in df.columns]
    out = df.rename(columns=str.lower)
    need = {"open", "high", "low", "close", "volume"}
    if not need.issubset(set(out.columns)):
        return None
    out = out[list(need)].dropna()
    return out if len(out) >= 5 else None


def _download(symbol: str, period: str, interval: str) -> pd.DataFrame | None:
    try:
        raw = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        return _normalize(raw)
    except Exception:
        return None


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame | None:
    try:
        out = df.resample("4h").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna()
        return out if len(out) >= 10 else None
    except Exception:
        return None


def _last_price(frames: dict[str, pd.DataFrame]) -> tuple[float, float]:
    for key in ("1D", "1H", "15M", "1W", "1M"):
        df = frames.get(key)
        if df is None or len(df) < 2:
            continue
        price = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-2])
        chg = ((price - prev) / prev) * 100 if prev else 0.0
        return price, chg
    return 2650.0, 0.0


def _synthetic_frames(base: float = 2650.0) -> dict[str, pd.DataFrame]:
    """Deterministic fallback OHLC when Yahoo is unavailable."""
    np.random.seed(42)
    frames: dict[str, pd.DataFrame] = {}
    specs = [("1D", 120), ("1H", 48), ("15M", 96)]
    price = base
    for label, n in specs:
        rows = []
        for i in range(n):
            shock = np.random.randn() * 0.003
            o = price
            c = price * (1 + shock)
            h = max(o, c) * (1 + abs(np.random.randn()) * 0.002)
            l = min(o, c) * (1 - abs(np.random.randn()) * 0.002)
            vol = int(5000 + abs(np.random.randn()) * 2000)
            rows.append({"open": o, "high": h, "low": l, "close": c, "volume": vol})
            price = c
        frames[label] = pd.DataFrame(rows)
    if "1H" in frames:
        frames["4H"] = _resample_4h(frames["1H"]) or frames["1H"]
    w = frames["1D"].copy()
    w = w.iloc[::5].reset_index(drop=True)
    if len(w) >= 10:
        frames["1W"] = w
    m = w.iloc[::4].reset_index(drop=True)
    if len(m) >= 10:
        frames["1M"] = m
    return frames


def _fetch_macro() -> dict[str, float | None]:
    macro: dict[str, float | None] = {}
    for sym, key in zip(PROXY_TICKERS, ("uup_chg", "tnx_chg", "dxy_chg")):
        df = _download(sym, "5d", "1d")
        if df is not None and len(df) > 1:
            c0, c1 = float(df["close"].iloc[-2]), float(df["close"].iloc[-1])
            macro[key] = round(((c1 - c0) / c0) * 100, 2) if c0 else 0.0
        else:
            macro[key] = None
        time.sleep(0.15)
    return macro


def _fetch_news(symbol: str) -> list[dict]:
    news: list[dict] = []
    try:
        for item in (yf.Ticker(symbol).news or [])[:12]:
            news.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
            })
    except Exception:
        pass
    return news


def fetch_gold_data(*, use_cache: bool = True) -> GoldMarketData:
    now = time.time()
    if use_cache and _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"]

    notes: list[str] = []
    frames: dict[str, pd.DataFrame] = {}
    symbol_used = GOLD_TICKERS[0]
    data_source = "live"

    for sym in GOLD_TICKERS:
        d1 = _download(sym, "2y", "1d")
        h1 = _download(sym, "60d", "1h")
        m15 = _download(sym, "5d", "15m")
        time.sleep(0.2)
        if d1 is not None:
            frames["1D"] = d1
            w = d1.iloc[::5].reset_index(drop=True)
            if len(w) >= 10:
                frames["1W"] = w
            m = d1.iloc[::22].reset_index(drop=True)
            if len(m) >= 10:
                frames["1M"] = m
        if h1 is not None:
            frames["1H"] = h1
            h4 = _resample_4h(h1)
            if h4 is not None:
                frames["4H"] = h4
        if m15 is not None:
            frames["15M"] = m15
        if frames:
            symbol_used = sym
            notes.append(f"Price data from {sym}.")
            break
        notes.append(f"{sym} unavailable.")

    if not frames:
        frames = _synthetic_frames()
        data_source = "fallback"
        notes.append("Yahoo Finance rate-limited or unreachable — using modelled fallback data.")
        notes.append("Agents still run; reconnect for live quotes.")

    price, chg = _last_price(frames)
    if data_source == "fallback":
        macro = {"uup_chg": None, "tnx_chg": None, "dxy_chg": None}
        news = []
    else:
        macro = _fetch_macro()
        news = _fetch_news(symbol_used)

    result = GoldMarketData(
        price=round(price, 2),
        change_pct=round(chg, 2),
        frames=frames,
        macro=macro,
        news=news,
        data_source=data_source,
        fetch_notes=notes,
    )
    _CACHE["data"] = result
    _CACHE["ts"] = now
    return result
