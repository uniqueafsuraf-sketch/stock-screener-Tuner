from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent.parent / "data" / "gold_war_room_history.json"
MAX_SCANS = 500
MAX_SCALPS = 500
MAX_SWING = 200


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
        "rr": trade.get("risk_reward"),
        "outcome": "open",
        "type": "swing",
    })
    data["setups"] = data["setups"][-MAX_SWING:]
    _save(data)


def record_war_room_cycle(payload: dict) -> None:
    """Log every agent scan + scalp opportunities for performance tracking."""
    data = _load()
    mb = payload.get("market_bias") or {}
    cm = payload.get("confidence_meter") or {}
    scalping = payload.get("scalping") or {}
    setups = scalping.get("setups") or []
    price = payload.get("price")

    data["scans"].append({
        "ts": time.time(),
        "logged_at": _utc_now(),
        "price": price,
        "change_pct": payload.get("change_pct"),
        "data_source": payload.get("data_source"),
        "bias": mb.get("bias"),
        "confidence": cm.get("score"),
        "scalps_found": len(setups),
        "consensus": (payload.get("agent_consensus") or {}).get("headline"),
    })
    data["scans"] = data["scans"][-MAX_SCANS:]

    for s in setups:
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
            "agent_votes": s.get("agent_votes"),
            "agents_aligned": s.get("agents_aligned"),
            "status": s.get("status"),
            "thesis": s.get("thesis"),
            "outcome": "open",
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
    closed = [s for s in setups if s.get("outcome") in ("win", "loss")]
    wins = sum(1 for s in closed if s["outcome"] == "win")
    losses = len(closed) - wins
    rr_vals = [s.get("rr") for s in setups if s.get("rr")]
    scalp_rr = [s.get("risk_reward") for s in scalps if s.get("risk_reward")]
    avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 0
    avg_scalp_rr = sum(scalp_rr) / len(scalp_rr) if scalp_rr else 0
    return {
        "total_setups": len(setups),
        "open_setups": sum(1 for s in setups if s.get("outcome") == "open"),
        "win_rate": round((wins / len(closed)) * 100, 1) if closed else 0,
        "loss_rate": round((losses / len(closed)) * 100, 1) if closed else 0,
        "average_rr": round(avg_rr, 2),
        "total_scans_logged": len(scans),
        "total_scalps_logged": len(scalps),
        "average_scalp_rr": round(avg_scalp_rr, 2),
        "last_scan_at": data.get("stats", {}).get("last_scan_at"),
        "accuracy_by_agent": data.get("stats", {}).get("by_agent", {}),
        "accuracy_by_condition": data.get("stats", {}).get("by_condition", {}),
        "accuracy_by_session": data.get("stats", {}).get("by_session", {}),
        "recent": setups[-8:][::-1],
        "recent_scalps": scalps[-12:][::-1],
        "recent_scans": scans[-8:][::-1],
        "log_file": "data/gold_war_room_history.json",
    }
