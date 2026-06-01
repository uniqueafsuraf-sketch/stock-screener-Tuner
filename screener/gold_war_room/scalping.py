"""Gold scalping desk — aggressive high-leverage setups anchored to live spot."""

from __future__ import annotations

from screener.gold_war_room.agents import _clamp, _pick_frame
from screener.gold_war_room.fetch import GoldMarketData


def _leverage_tier(leverage: int) -> str:
    if leverage >= 100:
        return "extreme"
    if leverage >= 50:
        return "aggressive"
    return "standard"


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


def _pct_move(entry: float, other: float, leverage: int) -> float:
    if not entry:
        return 0.0
    return round(abs(other - entry) / entry * leverage * 100, 1)


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
    tier: str,
) -> dict | None:
    is_long = direction == "LONG"
    entry = round(live, 2)
    stop = round(live - scalp_stop, 2) if is_long else round(live + scalp_stop, 2)
    target = round(live + scalp_target, 2) if is_long else round(live - scalp_target, 2)
    target_2_mult = 2.2 if tier == "extreme" else 1.8 if tier == "aggressive" else 1.6
    target_2 = round(live + scalp_target * target_2_mult, 2) if is_long else round(live - scalp_target * target_2_mult, 2)
    risk = abs(entry - stop) or 0.1
    reward = abs(target - entry)
    rr = round(reward / risk, 2)
    votes, voter_names = _agent_votes(agents, "long" if is_long else "short")
    manip = trap.get("manipulation_risk_score", 50)
    stop_hunt = trap.get("stop_hunt_prob", 50)

    min_rr = 3.5 if tier == "extreme" else 3.0 if tier == "aggressive" else 2.0
    min_votes = 1 if tier == "extreme" else 1 if tier == "aggressive" else 2
    manip_cap = 82 if tier in ("extreme", "aggressive") else 75

    confidence = _clamp(
        38
        + votes * 10
        + (15 if rr >= 4.5 else 10 if rr >= 3.5 else 5 if rr >= min_rr else 0)
        + (10 if vol_spike else 0)
        + (8 if tier == "extreme" else 4 if tier == "aggressive" else 0)
        - (manip * 0.12)
        - (12 if stop_hunt > 85 else 6 if stop_hunt > 75 else 0)
    )
    if votes < min_votes or rr < min_rr or manip > manip_cap:
        return None

    margin_pct = round((risk / entry) * leverage * 100, 2) if entry else 0
    gain_pct = _pct_move(entry, target, leverage)
    loss_pct = _pct_move(entry, stop, leverage)
    active_thresh = 58 if tier in ("extreme", "aggressive") else 65

    risk_labels = {
        "standard": "HIGH",
        "aggressive": "VERY HIGH",
        "extreme": "EXTREME",
    }

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
        "risk_profile": risk_labels[tier],
        "tier": tier,
        "margin_at_risk_pct": margin_pct,
        "gain_at_target_pct": gain_pct,
        "loss_at_stop_pct": loss_pct,
        "timeframe": "15M / 1H",
        "thesis": thesis,
        "status": "ACTIVE" if confidence >= active_thresh else "WATCH",
        "price_note": f"Tight stop {scalp_stop:.1f} pts · RR {rr}:1 @ ${entry}",
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
    leverage = max(10, min(200, int(leverage)))
    tier = _leverage_tier(leverage)
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

    if tier == "extreme":
        scalp_stop = round(max(1.8, atr_pts * 0.22), 2)
        scalp_target = round(scalp_stop * 5.5, 2)
    elif tier == "aggressive":
        scalp_stop = round(max(2.0, atr_pts * 0.32), 2)
        scalp_target = round(scalp_stop * 4.5, 2)
    else:
        scalp_stop = round(max(2.5, atr_pts * 0.45), 2)
        scalp_target = round(scalp_stop * 2.8, 2)

    vol_spike = False
    if m15 is not None:
        vol = m15["volume"]
        vol_spike = float(vol.iloc[-1]) > float(vol.tail(21).iloc[:-1].mean()) * 1.5

    candidates: list[tuple[str, str]] = []

    if of.get("stance") == "bullish" or tech.get("stance") == "bullish" or sweep_up > 55:
        candidates.append(("LONG", "High-RR long — flow/sweep · live anchor"))

    if of.get("stance") == "bearish" or tech.get("stance") == "bearish" or sweep_down > 55:
        candidates.append(("SHORT", "High-RR short — flow/sweep · live anchor"))

    if vol_spike and data.change_pct > 0.12:
        candidates.append(("LONG", "Volume impulse long — momentum scalp"))

    if vol_spike and data.change_pct < -0.12:
        candidates.append(("SHORT", "Volume impulse short — fade/momentum"))

    if tier in ("aggressive", "extreme"):
        if tech.get("stance") == "bullish":
            candidates.append(("LONG", f"{tier.upper()} leverage long — technical thrust"))
        if tech.get("stance") == "bearish":
            candidates.append(("SHORT", f"{tier.upper()} leverage short — technical breakdown"))

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
            tier=tier,
        )
        if row:
            setups.append(row)

    setups.sort(key=lambda x: (-x["confidence"], -x["risk_reward"], -x.get("gain_at_target_pct", 0)))
    best = setups[0] if setups else None
    tier_note = {
        "standard": "RR ≥2 · ≥2 agents",
        "aggressive": "Tight stops · RR ≥3 · 50x+ mode",
        "extreme": "Max risk/reward · RR ≥3.5 · 100x+ mode",
    }
    return {
        "title": "Live Scalping · High Risk / High Reward",
        "subtitle": f"{leverage}x · {tier.upper()} tier · live ${live} · 7 agents / 45s",
        "reference_price": live,
        "leverage": leverage,
        "tier": tier,
        "leverage_warning": (
            f"{leverage}x {tier} scalps: ~{scalp_stop:.1f} pt stop, ~{scalp_target:.1f} pt target. "
            f"At stop ≈{round((scalp_stop / live) * leverage * 100, 0)}% account risk; "
            f"at target ≈{round((scalp_target / live) * leverage * 100, 0)}% gain (illustrative). "
            "Liquidation risk is real — not financial advice."
        ),
        "scanning": True,
        "setups": setups[:8],
        "best": best,
        "total_found": len(setups),
        "criteria": tier_note[tier],
    }
