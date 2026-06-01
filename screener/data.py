from __future__ import annotations

import pandas as pd
import yfinance as yf


def fetch_history(symbol: str, lookback_days: int) -> pd.DataFrame | None:
    """Download daily OHLCV for one symbol."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f"{lookback_days}d", auto_adjust=True)
    if df is None or df.empty or len(df) < 30:
        return None
    df = df.rename(columns=str.lower)
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return None
    return df[["open", "high", "low", "close", "volume"]].dropna()


def fetch_batch(symbols: list[str], lookback_days: int) -> dict[str, pd.DataFrame]:
    """Download OHLCV for many symbols in one request (faster for dashboard)."""
    if not symbols:
        return {}

    period = f"{lookback_days}d"
    result: dict[str, pd.DataFrame] = {}

    # yfinance batch limit ~200; chunk if needed
    chunk_size = 80
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i : i + chunk_size]
        tickers = " ".join(chunk)
        raw = yf.download(
            tickers,
            period=period,
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
        if raw is None or raw.empty:
            continue

        if len(chunk) == 1:
            sym = chunk[0]
            df = _normalize_frame(raw)
            if df is not None and len(df) >= 30:
                result[sym] = df
            continue

        for sym in chunk:
            try:
                sub = raw[sym].copy()
            except (KeyError, TypeError):
                continue
            df = _normalize_frame(sub)
            if df is not None and len(df) >= 30:
                result[sym] = df

    return result


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.rename(columns=str.lower)
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(out.columns):
        return None
    out = out[list(required)].dropna()
    return out if not out.empty else None


def avg_dollar_volume(df: pd.DataFrame, window: int = 20) -> float:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return float((typical * df["volume"]).tail(window).mean())
