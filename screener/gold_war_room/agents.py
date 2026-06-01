from __future__ import annotations

import numpy as np
import pandas as pd

from screener.gold_war_room.fetch import GoldMarketData
from screener.signals import rsi


def _clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return float(max(lo, min(hi, v)))


def _trend_score(df: pd.DataFrame) -> tuple[float, float]:
    close = df["close"]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(min(50, len(close))).mean().iloc[-1]
    last = float(close.iloc[-1])
    bull = 50.0
    bear = 50.0
    if last > ma20:
        bull += 15
    else:
        bear += 15
    if last > ma50:
        bull += 20
    else:
        bear += 20
    slope = (float(close.iloc[-1]) - float(close.iloc[-10])) / max(float(close.iloc[-10]), 1e-9)
    if slope > 0.01:
        bull += 15
    elif slope < -0.01:
        bear += 15
    return _clamp(bull), _clamp(bear)


def _swing_levels(df: pd.DataFrame, window: int = 5) -> dict:
    highs, lows = df["high"].values, df["low"].values
    sh, sl = [], []
    half = window // 2
    for i in range(half, len(highs) - half):
        seg_h, seg_l = highs[i - half : i + half + 1], lows[i - half : i + half + 1]
        if highs[i] == seg_h.max():
            sh.append(float(highs[i]))
        if lows[i] == seg_l.min():
            sl.append(float(lows[i]))
    return {
        "resistance": sorted(set(round(x, 1) for x in sh[-6:]), reverse=True)[:4],
        "support": sorted(set(round(x, 1) for x in sl[-6:]))[:4],
    }


def agent_macro(data: GoldMarketData) -> dict:
    bull, bear = 50.0, 50.0
    reasons: list[str] = []
    dxy = data.macro.get("dxy_chg")
    tnx = data.macro.get("tnx_chg")
    if dxy is not None:
        if dxy > 0.15:
            bear += 18
            reasons.append(f"Dollar firm ({dxy:+.2f}% 1d) — headwind for gold.")
        elif dxy < -0.15:
            bull += 18
            reasons.append(f"Dollar soft ({dxy:+.2f}% 1d) — tailwind for gold.")
    if tnx is not None:
        if tnx > 0.5:
            bear += 12
            reasons.append(f"Yields rising ({tnx:+.2f}% 1d) — real-rate pressure on gold.")
        elif tnx < -0.5:
            bull += 12
            reasons.append(f"Yields easing ({tnx:+.2f}% 1d) — supportive for gold.")
    if data.change_pct > 0.4:
        bull += 8
        reasons.append("Gold bid on the day — risk-on / inflation hedge flow.")
    elif data.change_pct < -0.4:
        bear += 8
        reasons.append("Gold offered on the day — liquidation / USD bid.")
    kw_bull = sum(1 for n in data.news if any(w in (n.get("title") or "").lower() for w in ("fed cut", "geopolit", "safe haven", "inflation")))
    kw_bear = sum(1 for n in data.news if any(w in (n.get("title") or "").lower() for w in ("rate hike", "hawkish", "strong dollar", "nfp beat")))
    bull += min(15, kw_bull * 5)
    bear += min(15, kw_bear * 5)
    summary = " ".join(reasons[:3]) or "Macro mixed — monitor Fed, yields, and USD."
    return {
        "id": "macro",
        "name": "Macro Economist",
        "bullish_score": _clamp(bull),
        "bearish_score": _clamp(bear),
        "summary": summary,
        "stance": "bullish" if bull > bear + 8 else "bearish" if bear > bull + 8 else "neutral",
    }


def agent_technical(data: GoldMarketData) -> dict:
    bull, bear = 50.0, 50.0
    levels: dict[str, list] = {}
    notes: list[str] = []
    for tf, df in data.frames.items():
        b, s = _trend_score(df)
        bull = bull * 0.7 + b * 0.3
        bear = bear * 0.7 + s * 0.3
        lv = _swing_levels(df)
        levels[tf] = lv
    d1 = data.frames.get("1D")
    if d1 is not None and len(d1) > 30:
        r = rsi(d1["close"])
        if r < 35:
            bull += 10
            notes.append(f"Daily RSI {r:.0f} — oversold bounce potential.")
        elif r > 65:
            bear += 10
            notes.append(f"Daily RSI {r:.0f} — extended, mean-reversion risk.")
        hh = float(d1["high"].iloc[-20:].max())
        ll = float(d1["low"].iloc[-20:].min())
        last = float(d1["close"].iloc[-1])
        if last > (hh + ll) / 2:
            bull += 8
            notes.append("Price above mid-range — bullish structure bias.")
        else:
            bear += 8
            notes.append("Price below mid-range — bearish structure bias.")
    key = levels.get("1D") or levels.get("4H") or {"support": [], "resistance": []}
    return {
        "id": "technical",
        "name": "Technical Analyst",
        "bullish_score": _clamp(bull),
        "bearish_score": _clamp(bear),
        "stance": "bullish" if bull > bear + 8 else "bearish" if bear > bull + 8 else "neutral",
        "key_levels": key,
        "levels_by_tf": levels,
        "summary": " ".join(notes[:3]) or "Structure mixed across timeframes.",
    }


def agent_order_flow(data: GoldMarketData) -> dict:
    df = data.frames.get("15M") or data.frames.get("1H") or data.frames.get("1D")
    bull, bear = 50.0, 50.0
    liq: list[float] = []
    if df is None:
        return {
            "id": "order_flow", "name": "Order Flow Analyst",
            "bullish_score": 50, "bearish_score": 50, "stance": "neutral",
            "liquidity_levels": [], "summary": "Insufficient intraday data.",
        }
    body = (df["close"] - df["open"]).abs()
    vol = df["volume"]
    up_vol = vol.where(df["close"] >= df["open"], 0).tail(20).sum()
    down_vol = vol.where(df["close"] < df["open"], 0).tail(20).sum()
    total = up_vol + down_vol
    if total > 0:
        delta_ratio = (up_vol - down_vol) / total
        if delta_ratio > 0.15:
            bull += 22
        elif delta_ratio < -0.15:
            bear += 22
    vol_spike = float(vol.iloc[-1]) > float(vol.tail(21).iloc[:-1].mean()) * 1.6
    if vol_spike and float(df["close"].iloc[-1]) > float(df["open"].iloc[-1]):
        bull += 12
    elif vol_spike:
        bear += 12
    liq.append(round(float(df["high"].tail(30).max()), 1))
    liq.append(round(float(df["low"].tail(30).min()), 1))
    return {
        "id": "order_flow",
        "name": "Order Flow Analyst",
        "bullish_score": _clamp(bull),
        "bearish_score": _clamp(bear),
        "stance": "bullish" if bull > bear + 8 else "bearish" if bear > bull + 8 else "neutral",
        "liquidity_levels": liq,
        "summary": f"Recent delta bias {'buying' if bull > bear else 'selling' if bear > bull else 'balanced'}; "
        f"liquidity near {liq[0]} / {liq[1]}.",
    }


def agent_sentiment(data: GoldMarketData) -> dict:
    bull, bear = 45.0, 45.0
    titles = " ".join(n.get("title", "") for n in data.news).lower()
    if "rally" in titles or "record" in titles or "surge" in titles:
        bull += 15
    if "slump" in titles or "drop" in titles or "pressure" in titles:
        bear += 15
    if data.change_pct > 0:
        bull += 10
    else:
        bear += 10
    mood = "Risk-on gold bid" if bull > bear + 10 else "Defensive / cautious" if bear > bull + 10 else "Mixed mood"
    return {
        "id": "sentiment",
        "name": "Sentiment Analyst",
        "bullish_score": _clamp(bull),
        "bearish_score": _clamp(bear),
        "stance": "bullish" if bull > bear + 8 else "bearish" if bear > bull + 8 else "neutral",
        "market_mood": mood,
        "summary": f"{mood}. Headlines scanned: {len(data.news)} items.",
    }


def agent_risk(data: GoldMarketData, other_agents: list[dict]) -> dict:
    risk = 35.0
    warnings: list[str] = []
    avg_bull = sum(a["bullish_score"] for a in other_agents) / max(len(other_agents), 1)
    avg_bear = sum(a["bearish_score"] for a in other_agents) / max(len(other_agents), 1)
    if abs(avg_bull - avg_bear) < 12:
        risk += 20
        warnings.append("Agents disagree — conviction reduced.")
    d1 = data.frames.get("1D")
    if d1 is not None:
        atr = (d1["high"] - d1["low"]).tail(14).mean()
        pct_atr = (atr / float(d1["close"].iloc[-1])) * 100
        if pct_atr > 1.8:
            risk += 18
            warnings.append(f"Elevated volatility (ATR ~{pct_atr:.1f}% of price).")
    if data.macro.get("tnx_chg") and abs(data.macro["tnx_chg"]) > 1.0:
        risk += 12
        warnings.append("Large yield move — event risk for metals.")
    warnings.append("Black swan: geopolitical headline risk always present for gold.")
    conf_reduction = min(25, risk / 4)
    return {
        "id": "risk",
        "name": "Risk Manager",
        "risk_score": _clamp(risk),
        "warnings": warnings,
        "confidence_reduction": round(conf_reduction, 1),
        "stance": "warning" if risk > 55 else "neutral",
        "summary": warnings[0] if warnings else "Risk within normal bounds.",
    }


def agent_quant(data: GoldMarketData) -> dict:
    d1 = data.frames.get("1D")
    if d1 is None or len(d1) < 60:
        return {
            "id": "quant", "name": "Quant Analyst",
            "bull_probability": 50, "bear_probability": 50,
            "expected_move_range": "—", "stance": "neutral",
            "summary": "Insufficient history for quant model.",
        }
    rets = d1["close"].pct_change().dropna()
    up = (rets > 0).tail(60).mean() * 100
    bear_p = 100 - up
    atr = (d1["high"] - d1["low"]).tail(14).mean()
    last = float(d1["close"].iloc[-1])
    exp_lo, exp_hi = round(last - atr * 1.2, 1), round(last + atr * 1.2, 1)
    return {
        "id": "quant",
        "name": "Quant Analyst",
        "bull_probability": _clamp(up),
        "bear_probability": _clamp(bear_p),
        "expected_move_range": f"{exp_lo} – {exp_hi}",
        "stance": "bullish" if up > 55 else "bearish" if up < 45 else "neutral",
        "summary": f"60-day up-day rate {up:.0f}% — expected 1σ range {exp_lo}-{exp_hi}.",
    }


def agent_trap_detector(data: GoldMarketData) -> dict:
    df = data.frames.get("1H") or data.frames.get("1D")
    if df is None:
        base = 50.0
        return _trap_payload(base, base, base, base, base, base, base, "Limited data for trap analysis.")

    highs = df["high"].tail(40).values
    lows = df["low"].tail(40).values
    last_h, last_l = float(highs[-1]), float(lows[-1])
    eq_high = np.std(highs[-15:]) < (np.mean(highs[-15:]) * 0.002)
    eq_low = np.std(lows[-15:]) < (np.mean(lows[-15:]) * 0.002)
    sweep_up = 78.0 if eq_high else 52.0
    sweep_down = 75.0 if eq_low else 48.0
    stop_hunt = 72.0 if eq_low else 55.0
    fake_bo = 68.0 if eq_high and float(df["close"].iloc[-1]) < float(df["high"].iloc[-2]) else 45.0
    reversal = 62.0 if (eq_high or eq_low) else 40.0
    continuation = 58.0 if abs(data.change_pct) > 0.3 else 42.0
    manip = 70.0 if eq_high and eq_low else 48.0
    why = []
    if eq_high:
        why.append("Equal highs — liquidity pool above; upside sweep likely before reversal.")
    if eq_low:
        why.append("Equal lows — sell-side liquidity below; stop hunt risk.")
    return _trap_payload(sweep_up, sweep_down, stop_hunt, fake_bo, reversal, continuation, manip, " ".join(why))


def _trap_payload(
    sweep_up: float, sweep_down: float, stop_hunt: float, fake_bo: float,
    reversal: float, continuation: float, manip: float, explanation: str,
) -> dict:
    return {
        "id": "trap",
        "name": "Institutional Trap Detector",
        "liquidity_sweep_up_prob": _clamp(sweep_up),
        "liquidity_sweep_down_prob": _clamp(sweep_down),
        "stop_hunt_prob": _clamp(stop_hunt),
        "fake_breakout_prob": _clamp(fake_bo),
        "reversal_prob": _clamp(reversal),
        "trend_continuation_prob": _clamp(continuation),
        "manipulation_risk_score": _clamp(manip),
        "stance": "risky" if manip > 65 else "safe",
        "summary": explanation or "No dominant trap pattern.",
    }


def smart_money_intent(trap: dict, tech: dict, price: float) -> list[dict]:
    up = trap.get("liquidity_sweep_up_prob", 50)
    down = trap.get("liquidity_sweep_down_prob", 50)
    stop_h = trap.get("stop_hunt_prob", 50)
    cont = trap.get("trend_continuation_prob", 50)
    rev = trap.get("reversal_prob", 50)
    res = (tech.get("key_levels") or {}).get("resistance") or []
    sup = (tech.get("key_levels") or {}).get("support") or []
    target_up = f"{res[0]:.0f} – {res[0] + 7:.0f}" if res else f"{price + 15:.0f} – {price + 22:.0f}"
    target_down = f"{sup[0] - 7:.0f} – {sup[0]:.0f}" if sup else f"{price - 22:.0f} – {price - 15:.0f}"
    items = [
        {"label": "Upside Liquidity Sweep", "probability": up, "why": f"Target zone {target_up} — cluster above recent highs."},
        {"label": "Downside Stop Hunt", "probability": down, "why": f"Target zone {target_down} — liquidity under lows."},
        {"label": "Stop Hunt (aggregated)", "probability": stop_h, "why": "Retail stops likely clustered at obvious swing levels."},
        {"label": "Trend Continuation", "probability": cont, "why": "Momentum and structure alignment after liquidity event."},
        {"label": "Full Reversal", "probability": rev, "why": "Mean reversion after sweep / trap completion."},
    ]
    items.sort(key=lambda x: -x["probability"])
    return items


def liquidity_sweep_panel(trap: dict, tech: dict, price: float) -> dict:
    up, down = trap["liquidity_sweep_up_prob"], trap["liquidity_sweep_down_prob"]
    if up >= down:
        res = (tech.get("key_levels") or {}).get("resistance") or [price + 12]
        return {
            "direction": "Upside Sweep Likely",
            "target_zone": f"{res[0]:.0f} – {float(res[0]) + 7:.0f}",
            "probability": up,
            "explanation": trap.get("summary", "Liquidity above highs."),
        }
    sup = (tech.get("key_levels") or {}).get("support") or [price - 12]
    return {
        "direction": "Downside Sweep Likely",
        "target_zone": f"{float(sup[0]) - 7:.0f} – {sup[0]:.0f}",
        "probability": down,
        "explanation": "Liquidity below equal lows / swing lows.",
    }


def stop_hunt_panel(trap: dict) -> dict:
    p = trap["stop_hunt_prob"]
    level = "Extreme" if p > 85 else "High" if p > 70 else "Medium" if p > 50 else "Low"
    return {
        "probability": p,
        "risk_level": level,
        "explanation": f"Stop hunt probability {p:.0f}% — institutions may run obvious retail stop clusters.",
    }


def fake_breakout_panel(trap: dict) -> dict:
    fake = trap["fake_breakout_prob"]
    validity = _clamp(100 - fake)
    return {
        "breakout_validity_score": validity,
        "fake_breakout_probability": fake,
        "explanation": "High fake-breakout risk when price rejects after sweeping liquidity." if fake > 60 else "Breakout structure appears more valid.",
    }


def reversal_panel(trap: dict, tech: dict) -> dict:
    p = trap["reversal_prob"]
    sup = (tech.get("key_levels") or {}).get("support") or []
    res = (tech.get("key_levels") or {}).get("resistance") or []
    zone = f"{sup[0]:.0f} – {res[0]:.0f}" if sup and res else "Mid-range"
    return {
        "probability": p,
        "reversal_zone": zone,
        "confidence": _clamp(p * 0.85),
        "explanation": "Reversal more likely after liquidity grab at range extremes.",
    }


def trend_continuation_panel(trap: dict, macro: dict, tech: dict) -> dict:
    p = trap["trend_continuation_prob"]
    factors = []
    if macro.get("stance") == "bullish":
        factors.append("Macro tailwind")
    if tech.get("stance") == "bullish":
        factors.append("Technical trend alignment")
    if not factors:
        factors.append("Mixed context — continuation less reliable")
    return {
        "probability": p,
        "confidence": _clamp(p * 0.9),
        "supporting_factors": factors,
        "explanation": "Continuation favored when sweep already occurred and bias aligns.",
    }
