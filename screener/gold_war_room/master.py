from __future__ import annotations

from screener.gold_war_room.agents import _clamp


PRIMARY_AGENTS = ("macro", "technical", "order_flow", "sentiment", "quant")


def run_master(
    agents: dict[str, dict],
    trap: dict,
    risk: dict,
    price: float,
    tech: dict,
) -> dict:
    weights = {
        "macro": 1.1,
        "technical": 1.2,
        "order_flow": 1.0,
        "sentiment": 0.8,
        "quant": 1.0,
        "trap": 0.9,
    }
    bull_w, bear_w = 0.0, 0.0
    for key in PRIMARY_AGENTS:
        a = agents.get(key, {})
        w = weights.get(key, 1.0)
        bull_w += a.get("bullish_score", a.get("bull_probability", 50)) * w
        bear_w += a.get("bearish_score", a.get("bear_probability", 50)) * w

    trap_bias = (trap.get("liquidity_sweep_up_prob", 50) - trap.get("liquidity_sweep_down_prob", 50)) * 0.3
    bull_w += 50 * weights["trap"] + trap_bias
    bear_w += 50 * weights["trap"] - trap_bias

    total = bull_w + bear_w + 1e-9
    bull_p = _clamp((bull_w / total) * 100)
    bear_p = _clamp((bear_w / total) * 100)
    neutral_p = _clamp(100 - abs(bull_p - bear_p))

    if bull_p > bear_p + 12:
        bias = "Bullish"
    elif bear_p > bull_p + 12:
        bias = "Bearish"
    else:
        bias = "Neutral"

    confidence = _clamp((abs(bull_p - bear_p) + (100 - risk.get("risk_score", 50)) / 2) - risk.get("confidence_reduction", 0))

    live = round(float(price), 2)
    sup = (tech.get("key_levels") or {}).get("support") or [live - 8]
    res = (tech.get("key_levels") or {}).get("resistance") or [live + 8]
    if bias == "Bullish":
        entry = live
        stop = round(min(sup[0], live - 6), 2)
        t1 = round(live + 12, 2)
        t2 = round(live + 24, 2)
        t3 = round(live + 36, 2)
    else:
        entry = live
        stop = round(max(res[0], live + 6), 2)
        t1 = round(live - 12, 2)
        t2 = round(live - 24, 2)
        t3 = round(live - 36, 2)
    risk_pts = abs(entry - stop) or 1
    reward_pts = abs(t1 - entry)
    rr = round(reward_pts / risk_pts, 2)

    bullish_agree = sum(
        1 for k in PRIMARY_AGENTS
        if agents.get(k, {}).get("stance") == "bullish"
    )
    bearish_agree = sum(
        1 for k in PRIMARY_AGENTS
        if agents.get(k, {}).get("stance") == "bearish"
    )

    manip = trap.get("manipulation_risk_score", 50)
    show_trade = (
        confidence > 80
        and max(bullish_agree, bearish_agree) >= 4
        and rr > 2.5
        and manip < 70
    )

    trade = {
        "status": "HIGH_CONVICTION" if show_trade else "NO_HIGH_CONVICTION_TRADE",
        "direction": bias if show_trade else None,
        "entry_zone": f"{entry - 2:.0f} – {entry + 2:.0f}" if show_trade else None,
        "stop_loss": stop if show_trade else None,
        "target_1": t1 if show_trade else None,
        "target_2": t2 if show_trade else None,
        "target_3": t3 if show_trade else None,
        "risk_reward": rr if show_trade else None,
        "invalidation": round(res[0], 1) if bias == "Bullish" else round(sup[0], 1),
        "why": (
            f"Confidence {confidence:.0f}%, {max(bullish_agree, bearish_agree)}/5 primary agents align, "
            f"RR {rr}:1, manipulation risk {manip:.0f}%."
            if show_trade
            else f"Filters not met: confidence {confidence:.0f}% (need >80), "
            f"agent agreement {max(bullish_agree, bearish_agree)}/5 (need 4+), RR {rr} (need >2.5), "
            f"manipulation {manip:.0f}% (need <70)."
        ),
    }

    return {
        "market_bias": bias,
        "confidence_score": round(confidence, 1),
        "bull_probability": round(bull_p, 1),
        "bear_probability": round(bear_p, 1),
        "neutral_probability": round(neutral_p, 1),
        "trade": trade,
        "bullish_agents": bullish_agree,
        "bearish_agents": bearish_agree,
    }


def market_bias_display(
    bias: str,
    confidence: float,
    bull_p: float,
    bear_p: float,
    *,
    bullish_agents: int,
    bearish_agents: int,
) -> dict:
    """Plain-English copy for the Market Bias panel."""
    key = (bias or "Neutral").strip().lower()
    if key == "bullish":
        headline = "Gold is leaning BULLISH"
        meaning = (
            "Our desk sees more upward pressure than downward right now. "
            "Traders often watch for buy-the-dip entries or long scalps — always use stops and size for your risk."
        )
        lean_agents = bullish_agents
    elif key == "bearish":
        headline = "Gold is leaning BEARISH"
        meaning = (
            "Our desk sees more downward pressure than upward right now. "
            "Traders often stay cautious on longs and watch for sell rallies or short setups — always use stops."
        )
        lean_agents = bearish_agents
    else:
        headline = "Gold looks NEUTRAL"
        meaning = (
            "Bull and bear signals are roughly balanced. "
            "Many traders wait for a clearer lean before adding size — range tactics and tight stops often fit best."
        )
        lean_agents = max(bullish_agents, bearish_agents)

    if confidence >= 75:
        confidence_label = "Fairly sure"
    elif confidence >= 55:
        confidence_label = "Somewhat sure"
    elif confidence >= 35:
        confidence_label = "Not very sure"
    else:
        confidence_label = "Low conviction"

    agents_summary = (
        f"{lean_agents} of 5 core agents lean {bias.lower()}"
        if key in ("bullish", "bearish")
        else f"{bullish_agents} bullish · {bearish_agents} bearish among core agents"
    )

    return {
        "headline": headline,
        "meaning": meaning,
        "confidence_label": confidence_label,
        "agents_summary": agents_summary,
        "probability_detail": f"Model mix: {bull_p:.0f}% up · {bear_p:.0f}% down",
    }


def agent_consensus(agents: dict[str, dict], trap: dict, risk: dict) -> dict:
    rows = []
    mapping = [
        ("macro", "Macro"),
        ("technical", "Technical"),
        ("order_flow", "Order Flow"),
        ("sentiment", "Sentiment"),
        ("quant", "Quant"),
        ("risk", "Risk"),
        ("trap", "Trap Detector"),
    ]
    for key, label in mapping:
        if key == "trap":
            a = trap
        elif key == "risk":
            a = risk
        else:
            a = agents.get(key, {})
        if key == "risk":
            rows.append({"agent": label, "view": a.get("stance", "neutral").title(), "detail": a.get("summary", "")})
        elif key == "trap":
            rows.append({
                "agent": label,
                "view": "Risky" if a.get("stance") == "risky" else "Safe",
                "detail": a.get("summary", ""),
            })
        else:
            st = a.get("stance", "neutral")
            view = st.title() if st in ("bullish", "bearish", "neutral") else st.title()
            rows.append({"agent": label, "view": view, "detail": a.get("summary", "")})
    bull = sum(1 for r in rows if r["view"] == "Bullish")
    return {"rows": rows, "bullish_count": bull, "total": 7, "headline": f"{bull} / 7 Agents Bullish"}


def build_alerts(trap: dict) -> list[dict]:
    alerts: list[dict] = []
    checks = [
        ("liquidity_sweep_up_prob", 85, "Upside liquidity sweep alert"),
        ("liquidity_sweep_down_prob", 85, "Downside liquidity sweep alert"),
        ("stop_hunt_prob", 85, "Stop hunt alert"),
        ("fake_breakout_prob", 85, "Fake breakout alert"),
        ("manipulation_risk_score", 90, "Manipulation risk alert"),
        ("reversal_prob", 85, "Reversal alert"),
        ("trend_continuation_prob", 85, "Trend continuation alert"),
    ]
    for field, thresh, msg in checks:
        val = trap.get(field, 0)
        if val >= thresh:
            alerts.append({"type": field, "message": msg, "value": val})
    return alerts
