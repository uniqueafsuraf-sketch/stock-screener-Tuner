from __future__ import annotations

import json
import time
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent.parent / "data" / "gold_war_room_history.json"


def _load() -> dict:
    if not STORE.exists():
        return {"setups": [], "stats": {}}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"setups": [], "stats": {}}


def _save(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=0), encoding="utf-8")


def record_setup(master: dict, price: float) -> None:
    trade = master.get("trade") or {}
    if trade.get("status") != "HIGH_CONVICTION":
        return
    data = _load()
    data["setups"].append({
        "ts": time.time(),
        "price": price,
        "bias": master.get("market_bias"),
        "confidence": master.get("confidence_score"),
        "direction": trade.get("direction"),
        "entry": trade.get("entry_zone"),
        "stop": trade.get("stop_loss"),
        "target_1": trade.get("target_1"),
        "rr": trade.get("risk_reward"),
        "outcome": "open",
    })
    data["setups"] = data["setups"][-200:]
    _save(data)


def performance_summary() -> dict:
    data = _load()
    setups = data.get("setups") or []
    closed = [s for s in setups if s.get("outcome") in ("win", "loss")]
    wins = sum(1 for s in closed if s["outcome"] == "win")
    losses = len(closed) - wins
    rr_vals = [s.get("rr") for s in setups if s.get("rr")]
    avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 0
    return {
        "total_setups": len(setups),
        "open_setups": sum(1 for s in setups if s.get("outcome") == "open"),
        "win_rate": round((wins / len(closed)) * 100, 1) if closed else 0,
        "loss_rate": round((losses / len(closed)) * 100, 1) if closed else 0,
        "average_rr": round(avg_rr, 2),
        "accuracy_by_agent": data.get("stats", {}).get("by_agent", {}),
        "accuracy_by_condition": data.get("stats", {}).get("by_condition", {}),
        "accuracy_by_session": data.get("stats", {}).get("by_session", {}),
        "recent": setups[-10:][::-1],
    }
