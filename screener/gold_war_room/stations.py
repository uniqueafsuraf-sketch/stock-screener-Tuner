"""Agent operations center — station status and current work per agent."""

from __future__ import annotations

from screener.gold_war_room.fetch import GoldMarketData

STATION_META: dict[str, dict] = {
    "macro": {
        "station": "Global Macro Desk",
        "role": "Fed, yields, USD, geopolitical gold drivers",
        "icon": "MACRO",
    },
    "technical": {
        "station": "Chart Structure Lab",
        "role": "Multi-timeframe structure, RSI, key levels",
        "icon": "TECH",
    },
    "order_flow": {
        "station": "Order Flow Terminal",
        "role": "Volume delta, liquidity pools, intraday flow",
        "icon": "FLOW",
    },
    "sentiment": {
        "station": "News & Sentiment Wire",
        "role": "Headlines, market mood, narrative risk",
        "icon": "NEWS",
    },
    "quant": {
        "station": "Quant Research Pod",
        "role": "Historical stats, up-day rate, expected range",
        "icon": "QUANT",
    },
    "risk": {
        "station": "Risk Control Tower",
        "role": "Volatility, agent disagreement, conviction cut",
        "icon": "RISK",
    },
    "trap": {
        "station": "Trap Detection Unit",
        "role": "Liquidity sweeps, stop hunts, fake breakouts",
        "icon": "TRAP",
    },
}


def _status_from_agent(agent: dict) -> str:
    if agent.get("error"):
        return "error"
    st = agent.get("stance", "neutral")
    if st in ("warning", "risky"):
        return "warning"
    if st in ("bullish", "bearish"):
        return "active"
    return "idle"


def _working_on(agent_id: str, agent: dict, data: GoldMarketData, trap: dict, risk: dict) -> str:
    if agent.get("error"):
        return f"Recovering — {agent.get('error', 'unknown error')[:80]}"
    if agent_id == "macro":
        parts = []
        if data.macro.get("dxy_chg") is not None:
            parts.append(f"USD {data.macro['dxy_chg']:+.2f}%")
        if data.macro.get("tnx_chg") is not None:
            parts.append(f"10Y {data.macro['tnx_chg']:+.2f}%")
        return "Tracking " + (", ".join(parts) if parts else "macro feeds (cloud mode)") + f" · {len(data.news)} headlines"
    if agent_id == "technical":
        lv = agent.get("key_levels") or {}
        sup = lv.get("support") or []
        res = lv.get("resistance") or []
        return f"Mapping structure @ ${data.price:,.0f} · support {sup[0] if sup else '—'} / res {res[0] if res else '—'}"
    if agent_id == "order_flow":
        liq = agent.get("liquidity_levels") or []
        return f"Scanning 15M/1H tape · liquidity nodes {liq[0] if liq else '—'} / {liq[1] if len(liq) > 1 else '—'}"
    if agent_id == "sentiment":
        return f"Parsing {len(data.news)} gold headlines · mood: {agent.get('market_mood', 'scanning')}"
    if agent_id == "quant":
        return f"Running 60-day stats · expected range {agent.get('expected_move_range', '—')}"
    if agent_id == "risk":
        w = agent.get("warnings") or []
        return w[0] if w else f"Cross-checking 5 primary agents · risk score {agent.get('risk_score', 50)}"
    if agent_id == "trap":
        return (
            f"Sweep up {trap.get('liquidity_sweep_up_prob', 0):.0f}% · "
            f"sweep down {trap.get('liquidity_sweep_down_prob', 0):.0f}% · "
            f"manip {trap.get('manipulation_risk_score', 0):.0f}%"
        )
    return agent.get("summary", "Analyzing gold market…")[:120]


def _metrics_line(agent_id: str, agent: dict) -> str:
    if agent_id == "risk":
        return f"Risk {agent.get('risk_score', '—')} · Δ confidence {agent.get('confidence_reduction', 0)}"
    if agent_id == "trap":
        return f"Manip {agent.get('manipulation_risk_score', '—')}% · reversal {agent.get('reversal_prob', '—')}%"
    if agent.get("bull_probability") is not None:
        return f"Bull {agent.get('bull_probability')}% · Bear {agent.get('bear_probability')}%"
    if agent.get("bullish_score") is not None:
        return f"Bull {agent.get('bullish_score')} · Bear {agent.get('bearish_score')}"
    return ""


def build_agent_stations(
    agents: dict,
    trap: dict,
    risk: dict,
    data: GoldMarketData,
    *,
    scan_interval_sec: int = 45,
) -> dict:
    order = [
        ("macro", agents.get("macro", {})),
        ("technical", agents.get("technical", {})),
        ("order_flow", agents.get("order_flow", {})),
        ("sentiment", agents.get("sentiment", {})),
        ("quant", agents.get("quant", {})),
        ("risk", risk),
        ("trap", trap),
    ]
    rows: list[dict] = []
    active_count = 0
    for agent_id, agent in order:
        meta = STATION_META.get(agent_id, {})
        status = _status_from_agent(agent)
        if status == "active":
            active_count += 1
        rows.append({
            "id": agent_id,
            "name": agent.get("name") or meta.get("station", agent_id),
            "station": meta.get("station", agent_id),
            "desk_code": meta.get("icon", "AGENT"),
            "role": meta.get("role", ""),
            "status": status,
            "stance": (agent.get("stance") or "neutral").title(),
            "working_on": _working_on(agent_id, agent, data, trap, risk),
            "output": (agent.get("summary") or "")[:200],
            "metrics": _metrics_line(agent_id, agent),
            "has_error": bool(agent.get("error")),
        })
    return {
        "title": "Agent Operations Center",
        "subtitle": f"{active_count}/7 stations actively biased · full desk refresh every {scan_interval_sec}s",
        "scan_interval_sec": scan_interval_sec,
        "stations": rows,
        "headline": f"{active_count} agents on mission · 7 desks online",
    }
