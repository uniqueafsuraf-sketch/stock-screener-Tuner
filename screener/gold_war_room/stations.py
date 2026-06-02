"""Agent operations center — visual floor, overseers, live task labels."""

from __future__ import annotations

from screener.gold_war_room.fetch import GoldMarketData

STATION_META: dict[str, dict] = {
    "macro": {
        "station": "Global Macro Desk",
        "role": "Fed, yields, USD, geopolitical gold drivers",
        "desk_code": "MACRO",
        "character": "Agent Atlas",
        "avatar": "🌍",
        "accent": "macro",
    },
    "technical": {
        "station": "Chart Structure Lab",
        "role": "Multi-timeframe structure, RSI, key levels",
        "desk_code": "TECH",
        "character": "Agent Pixel",
        "avatar": "📊",
        "accent": "technical",
    },
    "order_flow": {
        "station": "Order Flow Terminal",
        "role": "Volume delta, liquidity pools, intraday flow",
        "desk_code": "FLOW",
        "character": "Agent Pulse",
        "avatar": "📡",
        "accent": "flow",
    },
    "sentiment": {
        "station": "News & Sentiment Wire",
        "role": "Headlines, market mood, narrative risk",
        "desk_code": "NEWS",
        "character": "Agent Echo",
        "avatar": "📰",
        "accent": "sentiment",
    },
    "quant": {
        "station": "Quant Research Pod",
        "role": "Historical stats, up-day rate, expected range",
        "desk_code": "QUANT",
        "character": "Agent Sigma",
        "avatar": "🔢",
        "accent": "quant",
    },
    "risk": {
        "station": "Risk Control Tower",
        "role": "Volatility, agent disagreement, conviction cut",
        "desk_code": "RISK",
        "character": "Agent Shield",
        "avatar": "🛡️",
        "accent": "risk",
    },
    "trap": {
        "station": "Trap Detection Unit",
        "role": "Liquidity sweeps, stop hunts, fake breakouts",
        "desk_code": "TRAP",
        "character": "Agent Snare",
        "avatar": "🎯",
        "accent": "trap",
    },
}

MAP_ROOMS: list[dict] = [
    {"id": "macro", "label": "Macro Wing", "x": 2, "y": 4, "w": 22, "h": 26},
    {"id": "technical", "label": "Chart Lab", "x": 76, "y": 4, "w": 22, "h": 26},
    {"id": "sentiment", "label": "News Wire", "x": 2, "y": 36, "w": 22, "h": 24},
    {"id": "command", "label": "Command Bridge", "x": 30, "y": 30, "w": 40, "h": 28},
    {"id": "order_flow", "label": "Flow Terminal", "x": 76, "y": 36, "w": 22, "h": 24},
    {"id": "quant", "label": "Quant Pod", "x": 2, "y": 68, "w": 22, "h": 26},
    {"id": "trap", "label": "Trap Unit", "x": 38, "y": 68, "w": 24, "h": 26},
    {"id": "risk", "label": "Risk Tower", "x": 76, "y": 68, "w": 22, "h": 26},
]

AGENT_MAP_SLOT: dict[str, dict] = {
    "macro": {"room": "macro", "x": 13, "y": 22},
    "technical": {"room": "technical", "x": 87, "y": 22},
    "sentiment": {"room": "sentiment", "x": 13, "y": 48},
    "order_flow": {"room": "order_flow", "x": 87, "y": 48},
    "quant": {"room": "quant", "x": 13, "y": 81},
    "trap": {"room": "trap", "x": 50, "y": 81},
    "risk": {"room": "risk", "x": 87, "y": 81},
    "boss": {"room": "command", "x": 44, "y": 46},
    "ops": {"room": "command", "x": 56, "y": 50},
}

CREW_COLORS: dict[str, str] = {
    "macro": "#e74c3c",
    "technical": "#3498db",
    "order_flow": "#2ecc71",
    "sentiment": "#f39c12",
    "quant": "#9b59b6",
    "risk": "#e67e22",
    "trap": "#ff6b9d",
    "boss": "#ffd700",
    "ops": "#00d4ff",
}

OVERSEER_META = {
    "boss": {
        "id": "boss",
        "station": "Command Bridge",
        "character": "Commander Vega",
        "avatar": "👑",
        "title": "Head Boss · Master Commander",
        "role": "Synthesizes all agent reports into one desk bias and trade plan",
        "accent": "boss",
    },
    "ops": {
        "id": "ops",
        "station": "Systems Control Room",
        "character": "Director Chen",
        "avatar": "⚙️",
        "title": "Operations Overseer",
        "role": "Keeps every agent online, evolving logic, and fixing issues",
        "accent": "ops",
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


def _task_label(agent_id: str, agent: dict, data: GoldMarketData, trap: dict, risk: dict) -> str:
    """Short label on the character — what they are doing right now."""
    if agent.get("error"):
        return "Fixing connection…"
    labels = {
        "macro": "Reading macro feeds",
        "technical": "Drawing key levels",
        "order_flow": "Watching live tape",
        "sentiment": "Scanning headlines",
        "quant": "Crunching stats",
        "risk": "Stress-testing desk",
        "trap": "Hunting liquidity traps",
    }
    return labels.get(agent_id, "Analyzing gold")


def _working_on(agent_id: str, agent: dict, data: GoldMarketData, trap: dict, risk: dict) -> str:
    if agent.get("error"):
        return f"Recovering — {agent.get('error', 'unknown error')[:100]}"
    if agent_id == "macro":
        parts = []
        if data.macro.get("dxy_chg") is not None:
            parts.append(f"USD {data.macro['dxy_chg']:+.2f}%")
        if data.macro.get("tnx_chg") is not None:
            parts.append(f"10Y {data.macro['tnx_chg']:+.2f}%")
        return "Tracking " + (", ".join(parts) if parts else "macro feeds") + f" · {len(data.news)} headlines queued"
    if agent_id == "technical":
        lv = agent.get("key_levels") or {}
        sup = lv.get("support") or []
        res = lv.get("resistance") or []
        return f"Mapping XAU @ ${data.price:,.2f} · support {sup[0] if sup else '—'} · resistance {res[0] if res else '—'}"
    if agent_id == "order_flow":
        liq = agent.get("liquidity_levels") or []
        return f"Reading 15M + 1H volume · pools at {liq[0] if liq else '—'} and {liq[1] if len(liq) > 1 else '—'}"
    if agent_id == "sentiment":
        return f"Reading {len(data.news)} stories · mood = {agent.get('market_mood', 'scanning')}"
    if agent_id == "quant":
        return f"60-day model · expected move {agent.get('expected_move_range', '—')}"
    if agent_id == "risk":
        w = agent.get("warnings") or []
        return w[0] if w else f"Checking 5 agents agree · risk score {agent.get('risk_score', 50)}"
    if agent_id == "trap":
        return (
            f"Sweep risk up {trap.get('liquidity_sweep_up_prob', 0):.0f}% · "
            f"down {trap.get('liquidity_sweep_down_prob', 0):.0f}% · "
            f"manipulation {trap.get('manipulation_risk_score', 0):.0f}%"
        )
    return (agent.get("summary") or "Analyzing gold…")[:140]


def _activity_mode(status: str) -> str:
    if status == "active":
        return "working"
    if status in ("warning", "error"):
        return "fixing"
    return "patrol"


def _intel_snippet(
    agent_id: str, agent: dict, data: GoldMarketData, trap: dict, risk: dict,
) -> str:
    """Best single-line intel for map HUD."""
    if agent.get("error"):
        return "Reconnecting feeds…"
    if agent_id == "macro":
        dxy = data.macro.get("dxy_chg")
        tnx = data.macro.get("tnx_chg")
        bits = []
        if dxy is not None:
            bits.append(f"DXY {dxy:+.2f}%")
        if tnx is not None:
            bits.append(f"10Y {tnx:+.2f}%")
        return " · ".join(bits) if bits else f"{len(data.news)} macro headlines"
    if agent_id == "technical":
        lv = agent.get("key_levels") or {}
        sup = (lv.get("support") or [None])[0]
        res = (lv.get("resistance") or [None])[0]
        return f"XAU ${data.price:,.0f} · S {sup or '—'} / R {res or '—'}"
    if agent_id == "order_flow":
        return (agent.get("summary") or "Flow scan")[:90]
    if agent_id == "sentiment":
        return f"Mood: {agent.get('market_mood', '—')} · {len(data.news)} stories"
    if agent_id == "quant":
        return f"Range {agent.get('expected_move_range', '—')} · up-day {agent.get('up_day_rate', '—')}"
    if agent_id == "risk":
        return f"Risk {agent.get('risk_score', 50)} · cut {agent.get('confidence_reduction', 0)} pts"
    if agent_id == "trap":
        return (
            f"Manip {trap.get('manipulation_risk_score', 0):.0f}% · "
            f"stop hunt {trap.get('stop_hunt_prob', 0):.0f}%"
        )
    return (agent.get("summary") or "")[:90]


def _agent_payload(
    agent_id: str,
    agent: dict,
    data: GoldMarketData,
    trap: dict,
    risk: dict,
    *,
    extra: dict | None = None,
) -> dict:
    meta = STATION_META.get(agent_id, {})
    status = _status_from_agent(agent)
    slot = AGENT_MAP_SLOT.get(agent_id, {"room": agent_id, "x": 50, "y": 70})
    base = {
        "id": agent_id,
        "name": meta.get("character") or agent.get("name") or agent_id,
        "character": meta.get("character", agent_id),
        "avatar": meta.get("avatar", "🤖"),
        "accent": meta.get("accent", "default"),
        "crew_color": CREW_COLORS.get(agent_id, "#7f8c8d"),
        "station": meta.get("station", agent_id),
        "desk_code": meta.get("desk_code", "AGENT"),
        "role": meta.get("role", ""),
        "map_room": slot["room"],
        "map_x": slot["x"],
        "map_y": slot["y"],
        "status": status,
        "activity": _activity_mode(status),
        "stance": (agent.get("stance") or "neutral").title(),
        "task_label": _task_label(agent_id, agent, data, trap, risk),
        "working_on": _working_on(agent_id, agent, data, trap, risk),
        "intel": _intel_snippet(agent_id, agent, data, trap, risk),
        "output": (agent.get("summary") or "")[:420],
        "metrics": _metrics_line(agent_id, agent),
        "warnings": list(agent.get("warnings") or [])[:4],
        "has_error": bool(agent.get("error")),
        "is_overseer": False,
        "tier": "analyst",
    }
    if extra:
        base.update(extra)
    return base


def _metrics_line(agent_id: str, agent: dict) -> str:
    if agent_id == "risk":
        return f"Risk {agent.get('risk_score', '—')} · confidence cut {agent.get('confidence_reduction', 0)}"
    if agent_id == "trap":
        return f"Manip {agent.get('manipulation_risk_score', '—')}% · reversal {agent.get('reversal_prob', '—')}%"
    if agent.get("bull_probability") is not None:
        return f"Up {agent.get('bull_probability')}% · down {agent.get('bear_probability')}%"
    if agent.get("bullish_score") is not None:
        return f"Bull score {agent.get('bullish_score')} · bear {agent.get('bearish_score')}"
    return ""


def _desk_health(agents: dict, trap: dict, risk: dict) -> dict:
    errors = [k for k, a in agents.items() if a.get("error")]
    warnings = [
        k for k, a in {**agents, "trap": trap, "risk": risk}.items()
        if _status_from_agent(a) in ("warning", "error")
    ]
    online = 7 - len(errors)
    return {
        "online": online,
        "total": 7,
        "errors": errors,
        "warnings": warnings,
        "all_ok": online == 7 and not errors,
    }


def _build_boss(master: dict | None, data: GoldMarketData, health: dict) -> dict:
    meta = OVERSEER_META["boss"]
    m = master or {}
    bias = m.get("market_bias", "Neutral")
    conf = m.get("confidence_score", 0)
    bull = m.get("bullish_agents", 0)
    bear = m.get("bearish_agents", 0)
    trade = m.get("trade") or {}
    if trade.get("status") == "HIGH_CONVICTION":
        working = f"Approving {trade.get('direction', '')} plan · entry ${data.price:,.0f} · RR {trade.get('risk_reward', '—')}"
        output = trade.get("why", "High-conviction setup cleared for desk.")
    else:
        working = f"Reviewing {bull} bullish vs {bear} bearish votes · final bias = {bias}"
        output = trade.get("why", f"Desk bias {bias} at {conf:.0f}% confidence — waiting for alignment.")
    status = "active" if conf >= 55 else "idle"
    if not health["all_ok"]:
        status = "warning"
    slot = AGENT_MAP_SLOT["boss"]
    return {
        **meta,
        "name": meta["character"],
        "status": status,
        "activity": _activity_mode(status),
        "stance": bias,
        "crew_color": CREW_COLORS["boss"],
        "map_room": slot["room"],
        "map_x": slot["x"],
        "map_y": slot["y"],
        "task_label": "Commanding the desk",
        "working_on": working,
        "intel": f"Desk {bias} · {conf:.0f}% confidence · {bull}B/{bear}S",
        "output": output[:420],
        "metrics": f"Confidence {conf:.0f}% · {bull}/5 bull · {bear}/5 bear",
        "is_overseer": True,
        "tier": "command",
    }


def _build_ops(
    agents: dict,
    health: dict,
    *,
    scan_interval_sec: int,
    live_scan: dict | None,
) -> dict:
    meta = OVERSEER_META["ops"]
    ls = live_scan or {}
    issues: list[str] = []
    if health["errors"]:
        issues.append(f"Recovering: {', '.join(health['errors'])}")
    if health["warnings"]:
        issues.append(f"Watching: {', '.join(health['warnings'])}")
    if not ls.get("active"):
        issues.append("Live scan loop idle — restarting cycle")

    if issues:
        working = " · ".join(issues)
        output = "Patching agent pipelines and re-running failed modules until green."
        status = "warning"
        task_label = "Fixing desk issues"
    else:
        working = (
            f"All {health['online']}/7 analyst stations online · "
            f"auto-scan every {scan_interval_sec}s · evolving trap + risk rules"
        )
        output = "Health check passed — feeds synced, consensus fresh, scalping engine armed."
        status = "active"
        task_label = "Monitoring all systems"

    slot = AGENT_MAP_SLOT["ops"]
    return {
        **meta,
        "name": meta["character"],
        "status": status,
        "activity": _activity_mode(status),
        "stance": "Operational" if health["all_ok"] else "Alert",
        "crew_color": CREW_COLORS["ops"],
        "map_room": slot["room"],
        "map_x": slot["x"],
        "map_y": slot["y"],
        "task_label": task_label,
        "working_on": working,
        "intel": f"{health['online']}/{health['total']} online · scan {scan_interval_sec}s",
        "output": output,
        "metrics": f"Uptime OK · scan {scan_interval_sec}s · {ls.get('agents_running', 7)} agents",
        "is_overseer": True,
        "tier": "ops",
        "health": health,
    }


def build_agent_stations(
    agents: dict,
    trap: dict,
    risk: dict,
    data: GoldMarketData,
    *,
    master: dict | None = None,
    live_scan: dict | None = None,
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
    health = _desk_health(agents, trap, risk)
    boss = _build_boss(master, data, health)
    ops = _build_ops(agents, health, scan_interval_sec=scan_interval_sec, live_scan=live_scan)

    rows: list[dict] = []
    active_count = 0
    for agent_id, agent in order:
        meta = STATION_META.get(agent_id, {})
        status = _status_from_agent(agent)
        if status == "active":
            active_count += 1
        rows.append(_agent_payload(agent_id, agent, data, trap, risk))

    floor_status = (
        "All agents running smoothly"
        if health["all_ok"]
        else f"{len(health['errors'])} agent(s) need attention · overseer active"
    )

    all_crew = [boss, ops] + rows
    return {
        "title": "Agent Operations Center",
        "subtitle": f"{active_count}/7 analysts on mission · Commander + Ops overseeing · refresh {scan_interval_sec}s",
        "scan_interval_sec": scan_interval_sec,
        "floor_status": floor_status,
        "health": health,
        "map_rooms": MAP_ROOMS,
        "overseers": [boss, ops],
        "stations": rows,
        "crew": all_crew,
        "headline": f"{len(all_crew)} crew on map · {active_count} actively working",
    }
