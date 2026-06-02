from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent.parent / "data" / "gold_war_room_history.json"
_STORE_LOCK = threading.Lock()
MAX_SCANS = 2000
MAX_SCALPS = 2000
MAX_SWING = 500
MAX_SIGNALS = 3000
SCALP_RESOLVE_SEC = 1200
SCAN_RESOLVE_SEC = 120
SCALP_DEDUPE_SEC = 90
SIGNAL_DEDUPE_SEC = 45


def _load() -> dict:
    with _STORE_LOCK:
        if not STORE.exists():
            return {"scans": [], "scalps": [], "setups": [], "signals": [], "stats": {}}
        try:
            data = json.loads(STORE.read_text(encoding="utf-8"))
            data.setdefault("scans", [])
            data.setdefault("scalps", [])
            data.setdefault("setups", [])
            data.setdefault("signals", [])
            data.setdefault("stats", {})
            return data
        except (json.JSONDecodeError, OSError):
            return {"scans": [], "scalps": [], "setups": [], "signals": [], "stats": {}}


def _save(data: dict) -> None:
    with _STORE_LOCK:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _live_price(payload: dict | None) -> float | None:
    if not payload:
        return None
    spot = payload.get("live_spot") or {}
    if spot.get("ok") and spot.get("price") is not None:
        return float(spot["price"])
    if payload.get("price") is not None:
        return float(payload["price"])
    return None


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
    if stop is None or target is None or not direction or entry is None:
        return

    try:
        stop_f = float(stop)
        target_f = float(target)
        entry_f = float(entry)
    except (TypeError, ValueError):
        return

    outcome = "open"
    if direction == "LONG":
        if price >= target_f:
            outcome = "win"
        elif price <= stop_f:
            outcome = "loss"
    elif direction == "SHORT":
        if price <= target_f:
            outcome = "win"
        elif price >= stop_f:
            outcome = "loss"

    age = now - float(trade.get("ts") or now)
    max_age = SCALP_RESOLVE_SEC if trade.get("type") == "scalp" else SCALP_RESOLVE_SEC * 2
    if outcome == "open" and age > max_age:
        outcome = "expired"

    if outcome == "open":
        return

    trade["outcome"] = outcome
    trade["resolved_at"] = _utc_now()
    trade["resolved_price"] = round(price, 2)
    trade["pnl_pts"] = round((price - entry_f) if direction == "LONG" else (entry_f - price), 2)
    aligned = trade.get("agents_aligned") or []
    trade["agents_correct"] = outcome == "win" and bool(aligned)
    trade["agents_wrong"] = outcome == "loss" and bool(aligned)
    trade["agent_verdict"] = "correct" if trade["agents_correct"] else "incorrect" if trade["agents_wrong"] else "neutral"


def _recompute_stats(data: dict) -> None:
    scalps = data.get("scalps") or []
    scans = data.get("scans") or []
    signals = data.get("signals") or []

    closed_scalps = [s for s in scalps if s.get("outcome") in ("win", "loss")]
    wins = sum(1 for s in closed_scalps if s["outcome"] == "win")
    expired = sum(1 for s in scalps if s.get("outcome") == "expired")
    correct_agents = sum(1 for s in closed_scalps if s.get("agents_correct"))
    scans_closed = [s for s in scans if s.get("agent_verdict") in ("correct", "incorrect")]
    scan_correct = sum(1 for s in scans_closed if s["agent_verdict"] == "correct")

    stats = data.setdefault("stats", {})
    stats["scalp_wins"] = wins
    stats["scalp_losses"] = len(closed_scalps) - wins
    stats["scalp_expired"] = expired
    stats["scalp_win_rate"] = round((wins / len(closed_scalps)) * 100, 1) if closed_scalps else 0
    stats["agent_scalp_accuracy"] = round((correct_agents / len(closed_scalps)) * 100, 1) if closed_scalps else 0
    stats["bias_call_accuracy"] = (
        round((scan_correct / len(scans_closed)) * 100, 1) if scans_closed else 0
    )
    stats["total_scans"] = len(scans)
    stats["total_scalps_logged"] = len(scalps)
    stats["total_signals_logged"] = len(signals)
    stats["open_scalps"] = sum(1 for s in scalps if s.get("outcome") == "open")
    stats["open_signals"] = sum(1 for s in signals if s.get("outcome") == "open")


def resolve_open_trades(price: float | None, *, payload: dict | None = None) -> None:
    """Mark wins/losses when live price hits stop or target."""
    if price is None:
        price = _live_price(payload)
    if price is None:
        return
    try:
        data = _load()
    except Exception:
        return
    now = time.time()
    for trade in (data.get("scalps") or [])[-80:]:
        if trade.get("outcome") == "open":
            _resolve_trade(trade, price, now)
    for trade in (data.get("setups") or [])[-40:]:
        if trade.get("outcome") == "open":
            _resolve_trade(trade, price, now)

    for sig in (data.get("signals") or [])[-120:]:
        if sig.get("track_trade") and sig.get("outcome") == "open":
            _resolve_trade(sig, price, now)

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

    _recompute_stats(data)
    _save(data)


def _scalp_signature(setup: dict) -> str:
    direction = (setup.get("direction") or "").upper()
    try:
        entry = round(float(setup.get("entry") or 0), 1)
    except (TypeError, ValueError):
        entry = 0
    status = setup.get("status") or "WATCH"
    return f"{direction}:{entry}:{status}"


def _scalp_already_open(data: dict, setup: dict) -> bool:
    sig = _scalp_signature(setup)
    now = time.time()
    for s in reversed(data.get("scalps") or []):
        if s.get("outcome") != "open":
            continue
        if _scalp_signature(s) != sig:
            continue
        if now - float(s.get("ts") or 0) < SCALP_DEDUPE_SEC:
            return True
    return False


def _signal_recently_logged(data: dict, signature: str) -> bool:
    now = time.time()
    for s in reversed(data.get("signals") or []):
        if s.get("signature") != signature:
            continue
        if now - float(s.get("ts") or 0) < SIGNAL_DEDUPE_SEC:
            return True
    return False


def _append_signal(
    data: dict,
    *,
    signature: str,
    category: str,
    label: str,
    detail: str,
    price: float | None,
    direction: str | None = None,
    strength: float | None = None,
    track_trade: bool = False,
    entry: float | None = None,
    stop: float | None = None,
    target: float | None = None,
    leverage: int | None = None,
    agents: list | None = None,
) -> None:
    if _signal_recently_logged(data, signature):
        return
    row = {
        "ts": time.time(),
        "logged_at": _utc_now(),
        "signature": signature,
        "category": category,
        "label": label,
        "detail": detail,
        "price": price,
        "direction": direction,
        "strength": strength,
        "outcome": "open",
        "track_trade": track_trade,
    }
    if track_trade and direction and entry is not None and stop is not None and target is not None:
        row.update({
            "entry": entry,
            "stop": stop,
            "target": target,
            "leverage": leverage,
            "agents_aligned": agents or [],
            "type": "signal_trade",
        })
    data["signals"].append(row)


def _record_signals_from_payload(data: dict, payload: dict, price: float | None) -> int:
    """Log agent alerts, desk conditions, and each scalp card as trackable signals."""
    added = 0
    before = len(data.get("signals") or [])

    for alert in payload.get("alerts") or []:
        atype = alert.get("type", "alert")
        val = alert.get("value", 0)
        _append_signal(
            data,
            signature=f"alert:{atype}:{int(val // 5) * 5}",
            category="alert",
            label=alert.get("message", atype),
            detail=f"Probability {round(val, 0)}%",
            price=price,
            strength=val,
        )

    for row in (payload.get("agent_consensus") or {}).get("rows") or []:
        view = (row.get("view") or "").lower()
        if view not in ("bullish", "bearish", "warning"):
            continue
        agent = row.get("agent", "Agent")
        _append_signal(
            data,
            signature=f"agent:{agent}:{view}",
            category="agent",
            label=f"{agent} → {row.get('view', '')}",
            detail=(row.get("detail") or "")[:120],
            price=price,
            direction="LONG" if view == "bullish" else "SHORT" if view == "bearish" else None,
            strength=70 if view in ("bullish", "bearish") else 55,
        )

    panels = (
        ("liquidity_sweep", payload.get("liquidity_sweep") or {}, "Liquidity sweep"),
        ("stop_hunt", payload.get("stop_hunt") or {}, "Stop hunt"),
        ("fake_breakout", payload.get("fake_breakout") or {}, "Fake breakout"),
        ("reversal", payload.get("reversal") or {}, "Reversal"),
        ("continuation", payload.get("trend_continuation") or {}, "Trend continuation"),
    )
    for key, panel, title in panels:
        prob = panel.get("probability") or panel.get("breakout_validity_score")
        if prob is None:
            continue
        try:
            prob_f = float(prob)
        except (TypeError, ValueError):
            continue
        if prob_f < 60:
            continue
        _append_signal(
            data,
            signature=f"panel:{key}:{int(prob_f // 10) * 10}",
            category="desk",
            label=f"{title} {round(prob_f, 0)}%",
            detail=(panel.get("explanation") or "")[:140],
            price=price,
            strength=prob_f,
        )

    trade = payload.get("trade_opportunity") or {}
    if trade.get("status") == "HIGH_CONVICTION":
        _append_signal(
            data,
            signature=f"swing:{trade.get('direction')}:{trade.get('entry_zone')}",
            category="swing",
            label=f"Swing {trade.get('direction', '')} HIGH CONVICTION",
            detail=trade.get("why", "")[:140],
            price=price,
            direction=(trade.get("direction") or "").upper() or None,
            strength=90,
            track_trade=True,
            entry=price,
            stop=_parse_level(trade.get("stop_loss")),
            target=_parse_level(trade.get("target_1")),
        )

    scalping = payload.get("scalping") or {}
    for setup in scalping.get("setups") or []:
        direction = (setup.get("direction") or "").upper()
        status = setup.get("status") or "WATCH"
        _append_signal(
            data,
            signature=f"scalp_sig:{_scalp_signature(setup)}",
            category="scalp",
            label=f"Scalp {direction} · {status}",
            detail=(setup.get("thesis") or setup.get("callout") or "")[:140],
            price=price,
            direction=direction,
            strength=setup.get("confidence"),
            track_trade=True,
            entry=float(setup.get("entry") or price or 0),
            stop=float(setup.get("stop") or 0),
            target=float(setup.get("target") or 0),
            leverage=setup.get("leverage"),
            agents=setup.get("agents_aligned"),
        )

    added = len(data.get("signals") or []) - before
    data["signals"] = data["signals"][-MAX_SIGNALS:]
    return added


def _parse_level(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("–", "-").split("-")[0].strip()
    try:
        return float(s)
    except ValueError:
        return None


def record_setup(master: dict, price: float) -> None:
    trade = master.get("trade") or {}
    if trade.get("status") != "HIGH_CONVICTION":
        return
    data = _load()
    stop = _parse_level(trade.get("stop_loss"))
    target = _parse_level(trade.get("target_1"))
    data["setups"].append({
        "ts": time.time(),
        "logged_at": _utc_now(),
        "price": price,
        "bias": master.get("market_bias"),
        "confidence": master.get("confidence_score"),
        "direction": trade.get("direction"),
        "entry": price,
        "stop": stop,
        "target": target,
        "target_1": trade.get("target_1"),
        "rr": trade.get("risk_reward"),
        "outcome": "open",
        "agent_verdict": "open",
        "type": "swing",
    })
    data["setups"] = data["setups"][-MAX_SWING:]
    _save(data)


def record_war_room_cycle(payload: dict) -> None:
    """Log scans, scalps, and every active desk signal; resolve open trades vs live spot."""
    price = _live_price(payload)
    resolve_open_trades(price, payload=payload)

    data = _load()
    mb = payload.get("market_bias") or {}
    cm = payload.get("confidence_meter") or {}
    scalping = payload.get("scalping") or {}
    setups = scalping.get("setups") or []
    consensus = payload.get("agent_consensus") or {}

    signals_added = _record_signals_from_payload(data, payload, price)

    data["scans"].append({
        "ts": time.time(),
        "logged_at": _utc_now(),
        "price": price,
        "change_pct": payload.get("change_pct"),
        "data_source": payload.get("data_source"),
        "bias": mb.get("bias"),
        "confidence": cm.get("score"),
        "scalps_found": len(setups),
        "signals_logged": signals_added,
        "consensus": consensus.get("headline"),
        "agent_verdict": "open",
    })
    data["scans"] = data["scans"][-MAX_SCANS:]

    for s in setups:
        if _scalp_already_open(data, s):
            continue
        entry = float(s.get("entry") or price or 0)
        data["scalps"].append({
            "ts": time.time(),
            "logged_at": _utc_now(),
            "market_price": price,
            "type": "scalp",
            "direction": s.get("direction"),
            "entry": entry,
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
            "callout": s.get("callout"),
            "outcome": "open",
            "agent_verdict": "open",
            "agents_correct": None,
            "signature": _scalp_signature(s),
        })
    data["scalps"] = data["scalps"][-MAX_SCALPS:]

    _recompute_stats(data)
    stats = data.setdefault("stats", {})
    stats["last_scan_at"] = _utc_now()
    _save(data)


def performance_summary() -> dict:
    data = _load()
    setups = data.get("setups") or []
    scalps = data.get("scalps") or []
    scans = data.get("scans") or []
    signals = data.get("signals") or []
    stats = data.get("stats") or {}

    closed_swing = [s for s in setups if s.get("outcome") in ("win", "loss")]
    swing_wins = sum(1 for s in closed_swing if s["outcome"] == "win")

    closed_scalps = [s for s in scalps if s.get("outcome") in ("win", "loss")]
    scalp_wins = sum(1 for s in closed_scalps if s["outcome"] == "win")
    scalp_losses = len(closed_scalps) - scalp_wins
    scalp_expired = sum(1 for s in scalps if s.get("outcome") == "expired")

    open_scalps = sum(1 for s in scalps if s.get("outcome") == "open")
    open_signals = sum(1 for s in signals if s.get("outcome") == "open")

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
        "total_signals_logged": len(signals),
        "open_scalps": open_scalps,
        "open_signals": open_signals,
        "scalp_wins": stats.get("scalp_wins", scalp_wins),
        "scalp_losses": stats.get("scalp_losses", scalp_losses),
        "scalp_expired": stats.get("scalp_expired", scalp_expired),
        "scalp_win_rate": stats.get("scalp_win_rate", 0),
        "agent_scalp_accuracy": stats.get("agent_scalp_accuracy", 0),
        "bias_call_accuracy": stats.get("bias_call_accuracy", 0),
        "average_scalp_rr": round(avg_scalp_rr, 2),
        "last_scan_at": stats.get("last_scan_at"),
        "accuracy_by_agent": stats.get("by_agent", {}),
        "accuracy_by_condition": stats.get("by_condition", {}),
        "accuracy_by_session": stats.get("by_session", {}),
        "recent": setups[-8:][::-1],
        "recent_scalps": scalps[-30:][::-1],
        "recent_scans": scans[-15:][::-1],
        "recent_signals": signals[-40:][::-1],
        "log_file": "data/gold_war_room_history.json",
    }
