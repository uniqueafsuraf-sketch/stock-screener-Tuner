"""Gold scalping desk — levels anchored to live spot price."""

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


def _build_scalp(
    *,
    direction: str,
    live: float,
    scalp_stop: float,
    scalp_target: float,
    thesis: str,
    agents: dict,
    trap: dict,
    leverage: int,
    vol_spike: bool,
) -> dict | None:
    is_long = direction == "LONG"
    entry = round(live, 2)
    stop = round(live - scalp_stop, 2) if is_long else round(live + scalp_stop, 2)
    target = round(live + scalp_target, 2) if is_long else round(live - scalp_target, 2)
    target_2 = round(live + scalp_target * 1.6, 2) if is_long else round(live - scalp_target * 1.6, 2)
    risk = abs(entry - stop) or 0.1
    reward = abs(target - entry)
    rr = round(reward / risk, 2)
    votes, voter_names = _agent_votes(agents, "long" if is_long else "short")
    manip = trap.get("manipulation_risk_score", 50)
    stop_hunt = trap.get("stop_hunt_prob", 50)
    confidence = _clamp(
        40
        + votes * 9
        + (12 if rr >= 2.5 else 0)
        + (8 if vol_spike else 0)
        - (manip * 0.15)
        - (10 if stop_hunt > 80 else 0)
    )
    if votes < 2 or rr < 2.0 or manip > 75:
        return None
    margin_pct = round((risk / entry) * leverage * 100, 2) if entry else 0
    return {
        "direction": direction,
        "market_price": entry,
        "entry": entry,
        "stop": stop,
        "target": target,
        "target_2": target_2,
        "risk_reward": rr,
        "confidence": round(confidence, 1),
        "agent_votes": votes,
        "agents_aligned": voter_names,
        "leverage": leverage,
        "margin_at_risk_pct": margin_pct,
        "timeframe": "15M / 1H",
        "thesis": thesis,
        "status": "ACTIVE" if confidence >= 65 else "WATCH",
        "price_note": f"Entry/stop/target anchored to live ${entry}",
    }


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
    live = round(float(price), 2)
    setups: list[dict] = []
    m15 = _pick_frame(data.frames, "15M", "1H")
    of = agents.get("order_flow", {})
    tech = agents.get("technical", {})
    sweep_up = trap.get("liquidity_sweep_up_prob", 50)
    sweep_down = trap.get("liquidity_sweep_down_prob", 50)

    atr_pts = 5.0
    if m15 is not None and len(m15) > 5:
        atr_pts = max(3.0, float((m15["high"] - m15["low"]).tail(14).mean()))
    scalp_stop = round(max(2.5, atr_pts * 0.45), 2)
    scalp_target = round(scalp_stop * 2.8, 2)

    vol_spike = False
    if m15 is not None:
        vol = m15["volume"]
        vol_spike = float(vol.iloc[-1]) > float(vol.tail(21).iloc[:-1].mean()) * 1.5

    candidates: list[tuple[str, str]] = []

    if of.get("stance") == "bullish" or tech.get("stance") == "bullish" or sweep_up > 58:
        candidates.append(("LONG", "Bullish flow / sweep — scalp from live price"))

    if of.get("stance") == "bearish" or tech.get("stance") == "bearish" or sweep_down > 58:
        candidates.append(("SHORT", "Bearish flow / sweep — scalp from live price"))

    if vol_spike and data.change_pct > 0.15:
        candidates.append(("LONG", "Volume spike momentum — 15M impulse"))

    if vol_spike and data.change_pct < -0.15:
        candidates.append(("SHORT", "Volume spike sell impulse — 15M fade"))

    if not candidates and tech.get("stance") == "bullish":
        candidates.append(("LONG", "Technical bias — watch long scalp"))
    elif not candidates and tech.get("stance") == "bearish":
        candidates.append(("SHORT", "Technical bias — watch short scalp"))

    seen: set[str] = set()
    for direction, thesis in candidates:
        if direction in seen:
            continue
        seen.add(direction)
        row = _build_scalp(
            direction=direction,
            live=live,
            scalp_stop=scalp_stop,
            scalp_target=scalp_target,
            thesis=thesis,
            agents=agents,
            trap=trap,
            leverage=leverage,
            vol_spike=vol_spike,
        )
        if row:
            setups.append(row)

    setups.sort(key=lambda x: (-x["confidence"], -x["risk_reward"]))
    best = setups[0] if setups else None
    return {
        "title": "Live Scalping Opportunities",
        "subtitle": f"{leverage}x leverage · live ${live} · 7 agents every 45s",
        "reference_price": live,
        "leverage": leverage,
        "leverage_warning": (
            f"High leverage ({leverage}x) magnifies gains and losses. "
            f"Stops are {scalp_stop:.1f} pts from live ${live} — not financial advice."
        ),
        "scanning": True,
        "setups": setups[:6],
        "best": best,
        "total_found": len(setups),
        "criteria": "Live price anchor · ≥2 agents · RR ≥2 · manip <75",
    }
