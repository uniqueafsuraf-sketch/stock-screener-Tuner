from __future__ import annotations

import pandas as pd

from screener.data import avg_dollar_volume
from screener.models import StockSnapshot


def year_range_from_df(df: pd.DataFrame, window: int = 252) -> tuple[float | None, float | None]:
    tail = df.tail(window)
    if tail.empty:
        return None, None
    return float(tail["high"].max()), float(tail["low"].min())


def detect_unusual_activity(snap: StockSnapshot, df: pd.DataFrame) -> tuple[list[str], float, float]:
    """
    Unusual activity flags (volume/price flow proxies).
    Returns: (activity tags, unusual_score 0-100, dollar_volume_millions)
    """
    tags: list[str] = []
    score = 0.0

    last = df.iloc[-1]
    price = float(last["close"])
    today_vol = float(last["volume"])
    dollar_vol = price * today_vol
    avg_dv = avg_dollar_volume(df)
    dollar_vol_m = dollar_vol / 1_000_000
    avg_dv_m = avg_dv / 1_000_000

    rvol = snap.volume_ratio

    # Relative volume tiers
    if rvol >= 4.0:
        tags.append("EXTREME_VOLUME")
        score += 35
    elif rvol >= 2.5:
        tags.append("UNUSUAL_VOLUME")
        score += 25
    elif rvol >= 1.8:
        tags.append("ELEVATED_VOLUME")
        score += 12

    # Price + volume combo (momentum flow)
    if abs(snap.change_pct) >= 5 and rvol >= 1.5:
        tags.append("VIOLENT_MOVE")
        score += 28
    elif abs(snap.change_pct) >= 3 and rvol >= 1.8:
        tags.append("PRICE_VOLUME_SPIKE")
        score += 22

    # Dollar flow vs typical
    if avg_dv_m > 0 and dollar_vol_m >= avg_dv_m * 2.5:
        tags.append("HEAVY_DOLLAR_FLOW")
        score += 20
    elif avg_dv_m > 0 and dollar_vol_m >= avg_dv_m * 1.8:
        score += 10

    # Gap + volume (opening drive)
    if snap.gap_pct is not None and abs(snap.gap_pct) >= 2 and rvol >= 1.5:
        tags.append("GAP_FLOW")
        score += 15

    # Range expansion today
    if len(df) >= 2:
        prev = df.iloc[-2]
        prev_range = float(prev["high"]) - float(prev["low"])
        today_range = float(last["high"]) - float(last["low"])
        if prev_range > 0 and today_range / prev_range >= 1.8:
            tags.append("RANGE_EXPANSION")
            score += 12

    # Breakout volume pattern
    if "BREAKOUT_SETUP" in snap.signals or "VOLUME_SPIKE" in snap.signals:
        tags.append("ACCUMULATION_WATCH")
        score += 10

    if "SELLOFF" in snap.signals and rvol >= 1.5:
        tags.append("CAPITULATION_FLOW")
        score += 14

    return tags, round(min(100, score), 1), round(dollar_vol_m, 2)
