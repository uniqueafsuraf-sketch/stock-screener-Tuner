"""Gold scalping desk — multi-agent 15M/1H opportunity scanner."""

from __future__ import annotations

from screener.gold_war_room.agents import _clamp, _pick_frame
from screener.gold_war_room.fetch import GoldMarketData


def _agent_votes(agents: dict, direction: str) -> tuple[int, list[str]]:
    votes = 0
    names: list[str] = []
    for key, label in (
        ("macro", "Macro"),
        ("technical", "Technical"),
        ("order_flow", "Order Flow"),
        ("sentiment", "Sentiment"),
        ("quant", "Quant"),
    ):
        a = agents.get(key, {})
        st = a.get("stance", "neutral")
        if direction == "long" and st == "bullish":
            votes += 1
            names.append(label)
        elif direction == "short" and st == "bearish":
            votes += 1
            names.append(label)
    return votes, names


def analyze_scalping_setups(
    data: GoldMarketData,
    agents: dict,
    trap: dict,
    technical: dict,
    price: float,
    *,
    leverage: int = 30,
) -> dict:
    leverage = max(10, min(50, int(leverage)))
    setups: list[dict] = []
    m15 = _pick_frame(data.frames, "15M", "1H")
    levels = technical.get("key_levels") or {}
    sup = levels.get("support") or [price - 6]
    res = levels.get("resistance") or [price + 6]
    manip = trap.get("manipulation_risk_score", 50)
    stop_hunt = trap.get("stop_hunt_prob", 50)
    sweep_up = trap.get("liquidity_sweep_up_prob", 50)
    sweep_down = trap.get("liquidity_sweep_down_prob", 50)
    of = agents.get("order_flow", {})
    tech = agents.get("technical", {})

    atr_pts = 5.0
    if m15 is not None and len(m15) > 5:
        atr_pts = max(3.0, float((m15["high"] - m15["low"]).tail(14).mean()))
    scalp_stop = round(max(2.5, atr_pts * 0.45), 1)
    scalp_target = round(scalp_stop * 2.8, 1)

    vol_spike = False
    if m15 is not None:
        vol = m15["volume"]
        vol_spike = float(vol.iloc[-1]) > float(vol.tail(21).iloc[:-1].mean()) * 1.5

    candidates: list[tuple[str, float, str]] = []

    if of.get("stance") == "bullish" or tech.get("stance") == "bullish" or sweep_up > 58:
        entry = round((float(sup[0]) + price) / 2, 1)
        stop = round(entry - scalp_stop, 1)
        target = round(entry + scalp_target, 1)
        candidates.append(("LONG", entry, "Liquidity sweep / bid stack — quick bounce scalp"))

    if of.get("stance") == "bearish" or tech.get("stance") == "bearish" or sweep_down > 58:
        entry = round((float(res[0]) + price) / 2, 1)
        stop = round(entry + scalp_stop, 1)
        target = round(entry - scalp_target, 1)
        candidates.append(("SHORT", entry, "Offer pressure / sweep highs — fade scalp"))

    if vol_spike and data.change_pct > 0.15:
        entry = round(price, 1)
        stop = round(price - scalp_stop, 1)
        target = round(price + scalp_target * 1.1, 1)
        candidates.append(("LONG", entry, "Volume spike momentum — 15M impulse scalp"))

    if vol_spike and data.change_pct < -0.15:
        entry = round(price, 1)
        stop = round(price + scalp_stop, 1)
        target = round(price - scalp_target * 1.1, 1)
        candidates.append(("SHORT", entry, "Volume spike sell impulse — 15M fade"))

    seen: set[str] = set()
    for direction, entry, thesis in candidates:
        key = f"{direction}:{entry}"
        if key in seen:
            continue
        seen.add(key)
        is_long = direction == "LONG"
        stop = round(entry - scalp_stop, 1) if is_long else round(entry + scalp_stop, 1)
        target = round(entry + scalp_target, 1) if is_long else round(entry - scalp_target, 1)
        risk = abs(entry - stop) or 0.1
        reward = abs(target - entry)
        rr = round(reward / risk, 2)
        votes, voter_names = _agent_votes(agents, "long" if is_long else "short")
        confidence = _clamp(
            40
            + votes * 9
            + (12 if rr >= 2.5 else 0)
            + (8 if vol_spike else 0)
            - (manip * 0.15)
            - (10 if stop_hunt > 80 else 0)
        )
        if votes < 2 or rr < 2.0 or manip > 75:
            continue
        margin_pct = round((risk / entry) * leverage * 100, 2) if entry else 0
        setups.append({
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "target_2": round(entry + scalp_target * 1.6, 1) if is_long else round(entry - scalp_target * 1.6, 1),
            "risk_reward": rr,
            "confidence": round(confidence, 1),
            "agent_votes": votes,
            "agents_aligned": voter_names,
            "leverage": leverage,
            "margin_at_risk_pct": margin_pct,
            "timeframe": "15M / 1H",
            "thesis": thesis,
            "status": "ACTIVE" if confidence >= 65 else "WATCH",
        })

    setups.sort(key=lambda x: (-x["confidence"], -x["risk_reward"]))
    best = setups[0] if setups else None
    return {
        "title": "Live Scalping Opportunities",
        "subtitle": f"{leverage}x leverage context · 7 agents scanning every 45s",
        "leverage": leverage,
        "leverage_warning": (
            f"High leverage ({leverage}x) magnifies gains and losses. "
            "A {0:.1f}pt adverse move can liquidate margin — not financial advice.".format(scalp_stop)
        ),
        "scanning": True,
        "setups": setups[:6],
        "best": best,
        "total_found": len(setups),
        "criteria": "≥2 agents align · RR ≥2 · manip <75 · 15M vol/flow",
    }
