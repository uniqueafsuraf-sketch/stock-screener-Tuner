from __future__ import annotations

import pandas as pd

from screener.edge import build_thesis, compute_edge_score, edge_grade
from screener.models import StockSnapshot
from screener.unusual import detect_unusual_activity, year_range_from_df


def spy_benchmark_change(df_spy: pd.DataFrame | None, days: int = 5) -> float | None:
    if df_spy is None or len(df_spy) < days + 1:
        return None
    close = df_spy["close"]
    return float((close.iloc[-1] / close.iloc[-days - 1] - 1) * 100)


def stock_return_pct(df: pd.DataFrame, days: int = 5) -> float | None:
    if len(df) < days + 1:
        return None
    close = df["close"]
    return float((close.iloc[-1] / close.iloc[-days - 1] - 1) * 100)


def compute_gap_pct(df: pd.DataFrame) -> float | None:
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev_close = float(df["close"].iloc[-2])
    open_px = float(last["open"])
    if prev_close <= 0:
        return None
    return round(((open_px - prev_close) / prev_close) * 100, 2)


def week52_position(price: float, year_high: float | None, year_low: float | None) -> float | None:
    if not year_high or not year_low or year_high <= year_low:
        return None
    return round((price - year_low) / (year_high - year_low), 3)


def estimate_risk_reward(snap: StockSnapshot) -> float | None:
    if snap.support_dist_pct is None and snap.resistance_dist_pct is None:
        return None
    upside = snap.resistance_dist_pct if snap.resistance_dist_pct is not None else 3.0
    downside = snap.support_dist_pct if snap.support_dist_pct is not None else 2.0
    if downside <= 0:
        downside = 1.0
    if upside <= 0:
        return None
    return round(upside / downside, 2)


def augment_snapshot(
    snap: StockSnapshot,
    df: pd.DataFrame,
    spy_5d: float | None = None,
) -> StockSnapshot:
    ret5 = stock_return_pct(df, 5)
    if ret5 is not None and spy_5d is not None:
        snap.vs_spy_5d = round(ret5 - spy_5d, 2)
    snap.momentum_5d = round(ret5, 2) if ret5 is not None else None
    snap.gap_pct = compute_gap_pct(df)

    yh, yl = year_range_from_df(df)
    snap.week52_position = week52_position(snap.price, yh, yl)
    snap.risk_reward = estimate_risk_reward(snap)

    tags, u_score, dvol = detect_unusual_activity(snap, df)
    snap.unusual_activity = tags
    snap.unusual_score = u_score
    snap.dollar_volume_m = dvol

    snap.edge_score = compute_edge_score(snap)
    snap.edge_grade = edge_grade(snap.edge_score)
    snap.thesis = build_thesis(snap)
    return snap


def build_scan_extras(all_stocks: list[StockSnapshot], cfg: dict) -> dict:
    gap_min = cfg.get("edge", {}).get("gap_min_pct", 1.5)
    unusual_min = cfg.get("unusual", {}).get("min_score", 25)

    edge_plays = sorted(all_stocks, key=lambda s: -s.edge_score)[:25]
    gainers = sorted(all_stocks, key=lambda s: -s.change_pct)[:15]
    losers = sorted(all_stocks, key=lambda s: s.change_pct)[:15]
    gaps = [s for s in all_stocks if s.gap_pct is not None and abs(s.gap_pct) >= gap_min]
    gaps.sort(key=lambda s: -abs(s.gap_pct))
    high_rvol = sorted(all_stocks, key=lambda s: -s.volume_ratio)[:15]
    rel_strength = sorted(
        [s for s in all_stocks if s.vs_spy_5d is not None],
        key=lambda s: -s.vs_spy_5d,
    )[:15]
    unusual = [s for s in all_stocks if s.unusual_score >= unusual_min]
    unusual.sort(key=lambda s: (-s.unusual_score, -s.volume_ratio))

    return {
        "edge_plays": [s.to_dict() for s in edge_plays],
        "gainers": [s.to_dict() for s in gainers],
        "losers": [s.to_dict() for s in losers],
        "gaps": [s.to_dict() for s in gaps[:20]],
        "high_rvol": [s.to_dict() for s in high_rvol],
        "rel_strength": [s.to_dict() for s in rel_strength],
        "unusual_activity": [s.to_dict() for s in unusual[:30]],
        "proprietary_signals": [
            {
                "id": "UNUSUAL",
                "name": "Unusual Activity",
                "desc": "Extreme volume, dollar flow, gap flow, and range expansion flags.",
            },
            {
                "id": "ALERTS",
                "name": "Price Alerts",
                "desc": "Real-time triggers on price, % change, volume, and unusual score.",
            },
            {
                "id": "EDGE_SCORE",
                "name": "Edge Score",
                "desc": "Proprietary 0–100 ranking for trade conviction.",
            },
        ],
    }
