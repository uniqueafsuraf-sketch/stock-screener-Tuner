from __future__ import annotations

import numpy as np
import pandas as pd

from screener.models import StockSnapshot

# Back-compat alias
Opportunity = StockSnapshot


def rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    val = 100 - (100 / (1 + rs))
    return float(val.iloc[-1]) if not val.empty and not np.isnan(val.iloc[-1]) else 50.0


def _swing_lows(lows: np.ndarray, window: int) -> list[tuple[int, float]]:
    points: list[tuple[int, float]] = []
    half = window // 2
    for i in range(half, len(lows) - half):
        segment = lows[i - half : i + half + 1]
        if lows[i] == segment.min():
            points.append((i, float(lows[i])))
    return points


def _swing_highs(highs: np.ndarray, window: int) -> list[tuple[int, float]]:
    points: list[tuple[int, float]] = []
    half = window // 2
    for i in range(half, len(highs) - half):
        segment = highs[i - half : i + half + 1]
        if highs[i] == segment.max():
            points.append((i, float(highs[i])))
    return points


def _trendline_value(points: list[tuple[int, float]], at_index: int) -> float | None:
    """Linear regression through last N swing points, projected to at_index."""
    if len(points) < 2:
        return None
    use = points[-4:] if len(points) >= 4 else points[-2:]
    xs = np.array([p[0] for p in use], dtype=float)
    ys = np.array([p[1] for p in use], dtype=float)
    if len(xs) < 2:
        return None
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope * at_index + intercept)


def evaluate(
    symbol: str,
    df: pd.DataFrame,
    *,
    volume_spike_ratio: float,
    selloff_min_pct: float,
    selloff_volume_ratio: float,
    trendline_proximity_pct: float,
    swing_window: int,
    rsi_period: int,
    rsi_oversold: float,
    avg_dollar_volume_m: float = 0.0,
) -> StockSnapshot:
    close = df["close"]
    volume = df["volume"]
    last = df.iloc[-1]
    prev_close = float(close.iloc[-2])
    price = float(last["close"])
    change_pct = ((price - prev_close) / prev_close) * 100

    avg_vol_20 = float(volume.tail(21).iloc[:-1].mean())
    today_vol = float(last["volume"])
    volume_ratio = today_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0

    snap = StockSnapshot(
        symbol=symbol,
        price=round(price, 2),
        change_pct=round(change_pct, 2),
        volume_ratio=round(volume_ratio, 2),
        rsi=round(rsi(close, rsi_period), 1),
        avg_dollar_volume_m=round(avg_dollar_volume_m, 1),
    )

    # --- Volume spike ---
    if volume_ratio >= volume_spike_ratio:
        snap.signals.append("VOLUME_SPIKE")
        direction = "up" if change_pct > 0 else "down"
        snap.notes.append(f"Volume {volume_ratio:.1f}x 20-day avg on a {direction} day")
        snap.score += 2

    # --- Sell-off (capitulation / bounce setup) ---
    if change_pct <= selloff_min_pct and volume_ratio >= selloff_volume_ratio:
        snap.signals.append("SELLOFF")
        snap.notes.append(f"Down {change_pct:.1f}% on elevated volume")
        snap.score += 2
        if snap.rsi <= rsi_oversold:
            snap.signals.append("OVERSOLD")
            snap.notes.append(f"RSI {snap.rsi} — potential mean-reversion bounce")
            snap.score += 1

    # --- Trendline proximity ---
    idx = len(df) - 1
    lows = df["low"].values
    highs = df["high"].values
    swing_low_pts = _swing_lows(lows, swing_window)
    swing_high_pts = _swing_highs(highs, swing_window)

    support_line = _trendline_value(swing_low_pts, idx)
    resistance_line = _trendline_value(swing_high_pts, idx)

    near_support = False
    near_resistance = False

    if support_line and support_line > 0:
        dist = ((price - support_line) / support_line) * 100
        snap.support_dist_pct = round(dist, 2)
        if 0 <= dist <= trendline_proximity_pct:
            near_support = True
            snap.signals.append("AT_SUPPORT")
            snap.notes.append(f"Price near rising support trendline (~${support_line:.2f})")
            snap.score += 2

    if resistance_line and resistance_line > 0:
        dist = ((resistance_line - price) / resistance_line) * 100
        snap.resistance_dist_pct = round(dist, 2)
        if 0 <= dist <= trendline_proximity_pct:
            near_resistance = True
            if "VOLUME_SPIKE" in snap.signals and change_pct > 0:
                snap.signals.append("BREAKOUT_SETUP")
                snap.notes.append(
                    f"Price testing resistance trendline (~${resistance_line:.2f}) with volume"
                )
                snap.score += 2
            else:
                snap.signals.append("AT_RESISTANCE")
                snap.notes.append(
                    f"Price near resistance trendline (~${resistance_line:.2f})"
                )
                snap.score += 1

    # Combined high-conviction patterns
    if "SELLOFF" in snap.signals and near_support:
        snap.signals.append("SELLOFF_AT_SUPPORT")
        snap.notes.append("Sell-off into support — watch for reversal confirmation")
        snap.score += 2

    snap.has_opportunity = len(snap.signals) > 0
    return snap


def analyze(
    symbol: str,
    df: pd.DataFrame,
    *,
    volume_spike_ratio: float,
    selloff_min_pct: float,
    selloff_volume_ratio: float,
    trendline_proximity_pct: float,
    swing_window: int,
    rsi_period: int,
    rsi_oversold: float,
) -> StockSnapshot | None:
    snap = evaluate(
        symbol,
        df,
        volume_spike_ratio=volume_spike_ratio,
        selloff_min_pct=selloff_min_pct,
        selloff_volume_ratio=selloff_volume_ratio,
        trendline_proximity_pct=trendline_proximity_pct,
        swing_window=swing_window,
        rsi_period=rsi_period,
        rsi_oversold=rsi_oversold,
    )
    return snap if snap.has_opportunity else None
