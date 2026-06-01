from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent.parent / "data" / "gold_war_room_history.json"
MAX_SCANS = 500
MAX_SCALPS = 500
MAX_SWING = 200
SCALP_RESOLVE_SEC = 1800
SCAN_RESOLVE_SEC = 120
SCALP_DEDUPE_SEC = 300


def _load() -> dict:
    if not STORE.exists():
        return {"scans": [], "scalps": [], "setups": [], "stats": {}}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        data.setdefault("scans", [])
        data.setdefault("scalps", [])
        data.setdefault("setups", [])
        data.setdefault("stats", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"scans": [], "scalps": [], "setups": [], "stats": {}}


def _save(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=0), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _bias_correct(bias: str | None, entry_price: float, exit_price: float) -> str | None:
    if not bias or bias.lower() in ("neutral", "—", ""):
        return "neutral"
    if not entry_price:
        return None
    delta_pct = ((exit_price - entry_price) / entry_price) * 100
    threshold = 0.05
    if bias.lower() in ("bullish", "long"):
        if delta_pct >= threshold:
            return "correct"
        if delta_pct <= -threshold:
            return "incorrect"
    elif bias.lower() in ("bearish", "short"):
        if delta_pct <= -threshold:
            return "correct"
        if delta_pct >= threshold:
            return "incorrect"
    return "neutral"


def _resolve_trade(trade: dict, price: float, now: float) -> None:
    if trade.get("outcome") not in (None, "open"):
        return
    direction = (trade.get("direction") or "").upper()
    stop = trade.get("stop")
    target = trade.get("target")
    entry = trade.get("entry") or trade.get("market_price")
    if stop is None or target is None or not direction:
        return

    outcome = "open"
    if direction == "LONG":
        if price >= target:
            outcome = "win"
        elif price <= stop:
            outcome = "loss"
    elif direction == "SHORT":
        if price <= target:
            outcome = "win"
        elif price >= stop:
            outcome = "loss"

    age = now - float(trade.get("ts") or now)
    if outcome == "open" and age > SCALP_RESOLVE_SEC:
        outcome = "expired"

    if outcome == "open":
        return

    trade["outcome"] = outcome
    trade["resolved_at"] = _utc_now()
    trade["resolved_price"] = round(price, 2)
    if entry:
        trade["pnl_pts"] = round((price - entry) if direction == "LONG" else (entry - price), 2)
    aligned = trade.get("agents_aligned") or []
    trade["agents_correct"] = outcome == "win" and bool(aligned)
    trade["agents_wrong"] = outcome == "loss" and bool(aligned)


def resolve_open_trades(price: float | None) -> None:
    """Mark wins/losses when live price hits stop or target."""
    if price is None:
        return
    data = _load()
    now = time.time()
    for trade in data.get("scalps") or []:
        _resolve_trade(trade, price, now)
    for trade in data.get("setups") or []:
        _resolve_trade(trade, price, now)

    scans = data.get("scans") or []
    for prev in scans:
        if prev.get("agent_verdict") not in (None, "open"):
            continue
        if not prev.get("price"):
            continue
        age = now - float(prev.get("ts") or now)
        if age < SCAN_RESOLVE_SEC:
            continue
        verdict = _bias_correct(prev.get("bias"), float(prev["price"]), float(price))
        if verdict:
            prev["agent_verdict"] = verdict
            prev["verdict_price"] = round(price, 2)
            prev["price_delta_pct"] = round(
                ((price - prev["price"]) / prev["price"]) * 100, 3
            )

    stats = data.setdefault("stats", {})
    scalps = data.get("scalps") or []
    closed_scalps = [s for s in scalps if s.get("outcome") in ("win", "loss")]
    wins = sum(1 for s in closed_scalps if s["outcome"] == "win")
    correct_agents = sum(1 for s in closed_scalps if s.get("agents_correct"))
    scans_closed = [s for s in scans if s.get("agent_verdict") in ("correct", "incorrect")]
    scan_correct = sum(1 for s in scans_closed if s["agent_verdict"] == "correct")

    stats["scalp_wins"] = wins
    stats["scalp_losses"] = len(closed_scalps) - wins
    stats["scalp_win_rate"] = round((wins / len(closed_scalps)) * 100, 1) if closed_scalps else 0
    stats["agent_scalp_accuracy"] = round((correct_agents / len(closed_scalps)) * 100, 1) if closed_scalps else 0
    stats["bias_call_accuracy"] = (
        round((scan_correct / len(scans_closed)) * 100, 1) if scans_closed else 0
    )
    _save(data)


def _scalp_already_open(data: dict, setup: dict) -> bool:
    direction = setup.get("direction")
    now = time.time()
    for s in reversed(data.get("scalps") or []):
        if s.get("outcome") != "open":
            continue
        if s.get("direction") != direction:
            continue
        if now - float(s.get("ts") or 0) < SCALP_DEDUPE_SEC:
            return True
    return False


def record_setup(master: dict, price: float) -> None:
    trade = master.get("trade") or {}
    if trade.get("status") != "HIGH_CONVICTION":
        return
    data = _load()
    data["setups"].append({
        "ts": time.time(),
        "logged_at": _utc_now(),
        "price": price,
        "bias": master.get("market_bias"),
        "confidence": master.get("confidence_score"),
        "direction": trade.get("direction"),
        "entry": trade.get("entry_zone"),
        "stop": trade.get("stop_loss"),
        "target_1": trade.get("target_1"),
        "target": trade.get("target_1"),
        "rr": trade.get("risk_reward"),
        "outcome": "open",
        "agent_verdict": "open",
        "type": "swing",
    })
    data["setups"] = data["setups"][-MAX_SWING:]
    _save(data)


def record_war_room_cycle(payload: dict) -> None:
    """Log scans + scalps; resolve prior trades against live price."""
    price = payload.get("price")
    resolve_open_trades(price)

    data = _load()
    mb = payload.get("market_bias") or {}
    cm = payload.get("confidence_meter") or {}
    scalping = payload.get("scalping") or {}
    setups = scalping.get("setups") or []
    consensus = payload.get("agent_consensus") or {}

    data["scans"].append({
        "ts": time.time(),
        "logged_at": _utc_now(),
        "price": price,
        "change_pct": payload.get("change_pct"),
        "data_source": payload.get("data_source"),
        "bias": mb.get("bias"),
        "confidence": cm.get("score"),
        "scalps_found": len(setups),
        "consensus": consensus.get("headline"),
        "agent_verdict": "open",
    })
    data["scans"] = data["scans"][-MAX_SCANS:]

    for s in setups:
        if _scalp_already_open(data, s):
            continue
        data["scalps"].append({
            "ts": time.time(),
            "logged_at": _utc_now(),
            "market_price": price,
            "type": "scalp",
            "direction": s.get("direction"),
            "entry": s.get("entry"),
            "stop": s.get("stop"),
            "target": s.get("target"),
            "target_2": s.get("target_2"),
            "risk_reward": s.get("risk_reward"),
            "confidence": s.get("confidence"),
            "leverage": s.get("leverage"),
            "risk_profile": s.get("risk_profile"),
            "gain_at_target_pct": s.get("gain_at_target_pct"),
            "loss_at_stop_pct": s.get("loss_at_stop_pct"),
            "agent_votes": s.get("agent_votes"),
            "agents_aligned": s.get("agents_aligned"),
            "status": s.get("status"),
            "thesis": s.get("thesis"),
            "outcome": "open",
            "agent_verdict": "open",
            "agents_correct": None,
        })
    data["scalps"] = data["scalps"][-MAX_SCALPS:]

    stats = data.setdefault("stats", {})
    stats["last_scan_at"] = _utc_now()
    stats["total_scans"] = len(data["scans"])
    stats["total_scalps_logged"] = len(data["scalps"])
    stats["total_swing_setups"] = len(data["setups"])
    _save(data)


def performance_summary() -> dict:
    data = _load()
    setups = data.get("setups") or []
    scalps = data.get("scalps") or []
    scans = data.get("scans") or []
    stats = data.get("stats") or {}

    closed_swing = [s for s in setups if s.get("outcome") in ("win", "loss")]
    swing_wins = sum(1 for s in closed_swing if s["outcome"] == "win")

    closed_scalps = [s for s in scalps if s.get("outcome") in ("win", "loss")]
    scalp_wins = sum(1 for s in closed_scalps if s["outcome"] == "win")
    scalp_losses = len(closed_scalps) - scalp_wins

    open_scalps = sum(1 for s in scalps if s.get("outcome") == "open")
    scans_verdict = [s for s in scans if s.get("agent_verdict") in ("correct", "incorrect", "neutral")]

    rr_vals = [s.get("rr") for s in setups if s.get("rr")]
    scalp_rr = [s.get("risk_reward") for s in scalps if s.get("risk_reward")]
    avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 0
    avg_scalp_rr = sum(scalp_rr) / len(scalp_rr) if scalp_rr else 0

    return {
        "total_setups": len(setups),
        "open_setups": sum(1 for s in setups if s.get("outcome") == "open"),
        "win_rate": round((swing_wins / len(closed_swing)) * 100, 1) if closed_swing else 0,
        "loss_rate": round(((len(closed_swing) - swing_wins) / len(closed_swing)) * 100, 1) if closed_swing else 0,
        "average_rr": round(avg_rr, 2),
        "total_scans_logged": len(scans),
        "total_scalps_logged": len(scalps),
        "open_scalps": open_scalps,
        "scalp_wins": stats.get("scalp_wins", scalp_wins),
        "scalp_losses": stats.get("scalp_losses", scalp_losses),
        "scalp_win_rate": stats.get("scalp_win_rate", 0),
        "agent_scalp_accuracy": stats.get("agent_scalp_accuracy", 0),
        "bias_call_accuracy": stats.get("bias_call_accuracy", 0),
        "average_scalp_rr": round(avg_scalp_rr, 2),
        "last_scan_at": stats.get("last_scan_at"),
        "accuracy_by_agent": stats.get("by_agent", {}),
        "accuracy_by_condition": stats.get("by_condition", {}),
        "accuracy_by_session": stats.get("by_session", {}),
        "recent": setups[-8:][::-1],
        "recent_scalps": scalps[-15:][::-1],
        "recent_scans": scans[-10:][::-1],
        "log_file": "data/gold_war_room_history.json",
    }
