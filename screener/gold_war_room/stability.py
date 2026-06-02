"""Desk stability agent — keeps War Room cache healthy and trims heavy history."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from screener.runtime import is_cloud_host

HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gold_war_room_history.json"
MAX_HISTORY_BYTES = 1_500_000
STUCK_COMPUTE_SEC = 90


def slim_war_room_payload(payload: dict | None) -> dict:
    """Small JSON for HTML embed; full desk loads via /api/gold-war-room."""
    if not payload:
        return {
            "ok": True,
            "warming": True,
            "message": "Loading agents…",
            "market_bias": {"headline": "Loading…", "meaning": ""},
            "confidence_meter": {"score": 0, "label": "—"},
            "agents": {},
            "agent_consensus": {"rows": [], "headline": "—"},
        }
    chart = payload.get("chart") or {}
    perf = payload.get("performance") or {}
    agents_slim = {}
    for key, agent in (payload.get("agents") or {}).items():
        if not isinstance(agent, dict):
            continue
        agents_slim[key] = {
            "stance": agent.get("stance"),
            "summary": (agent.get("summary") or "")[:180],
        }
    return {
        "ok": payload.get("ok", True),
        "warming": payload.get("warming"),
        "error": payload.get("error"),
        "price": payload.get("price"),
        "change_pct": payload.get("change_pct"),
        "updated_at": payload.get("updated_at"),
        "price_symbol": payload.get("price_symbol"),
        "market_bias": payload.get("market_bias"),
        "confidence_meter": payload.get("confidence_meter"),
        "agent_consensus": payload.get("agent_consensus"),
        "agents": agents_slim,
        "alerts": (payload.get("alerts") or [])[:8],
        "scalping": {
            "title": (payload.get("scalping") or {}).get("title"),
            "subtitle": (payload.get("scalping") or {}).get("subtitle"),
            "leverage": (payload.get("scalping") or {}).get("leverage"),
            "setups": ((payload.get("scalping") or {}).get("setups") or [])[:4],
            "leverage_callout": (payload.get("scalping") or {}).get("leverage_callout"),
        },
        "live_scan": payload.get("live_scan"),
        "agent_stations": {
            "title": (payload.get("agent_stations") or {}).get("title"),
            "headline": (payload.get("agent_stations") or {}).get("headline"),
            "floor_status": (payload.get("agent_stations") or {}).get("floor_status"),
            "stations": ((payload.get("agent_stations") or {}).get("stations") or [])[:8],
        },
        "performance": {
            "total_signals_logged": perf.get("total_signals_logged", 0),
            "total_scalps_logged": perf.get("total_scalps_logged", 0),
            "open_scalps": perf.get("open_scalps", 0),
            "scalp_wins": perf.get("scalp_wins", 0),
            "scalp_losses": perf.get("scalp_losses", 0),
        },
        "chart": {
            "symbol": chart.get("symbol", "XAUUSD"),
            "tv_symbol": chart.get("tv_symbol", "OANDA:XAUUSD"),
            "candles": [],
            "interval": chart.get("interval", "1H"),
        },
        "news": (payload.get("news") or [])[:6],
    }


def trim_history_file() -> dict:
    """Cap history size so resolve/summary stays fast on Render."""
    if not HISTORY_PATH.exists():
        return {"trimmed": False, "bytes": 0}
    try:
        raw = HISTORY_PATH.read_text(encoding="utf-8")
        size = len(raw.encode("utf-8"))
        if size <= MAX_HISTORY_BYTES:
            return {"trimmed": False, "bytes": size}
        data = json.loads(raw)
        for key, limit in (
            ("signals", 400),
            ("scalps", 400),
            ("scans", 300),
            ("setups", 80),
        ):
            if isinstance(data.get(key), list) and len(data[key]) > limit:
                data[key] = data[key][-limit:]
        HISTORY_PATH.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        new_size = HISTORY_PATH.stat().st_size
        return {"trimmed": True, "bytes": new_size, "before": size}
    except Exception as e:
        traceback.print_exc()
        return {"trimmed": False, "error": str(e)}


def run_watchdog_tick(
    *,
    war_room_cache: dict,
    war_room_lock,
    reset_compute_fn,
    load_seed_fn,
    war_room_ready_fn,
) -> dict:
    """
    Stability pass: unstuck compute lock, ensure cache, trim history.
    Called from a background thread in dashboard.server.
    """
    report: dict = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "cloud": is_cloud_host(),
        "actions": [],
    }

    with war_room_lock:
        computing = war_room_cache.get("computing", False)
        started = war_room_cache.get("computing_since") or 0.0
        cached = war_room_cache.get("data")

    if computing and started and (time.time() - started) > STUCK_COMPUTE_SEC:
        reset_compute_fn()
        report["actions"].append("reset_stuck_compute")

    if not war_room_ready_fn(cached):
        if load_seed_fn():
            report["actions"].append("reloaded_seed_cache")
        else:
            report["actions"].append("seed_missing")

    trim = trim_history_file()
    if trim.get("trimmed"):
        report["actions"].append(f"trimmed_history:{trim.get('before')}->{trim.get('bytes')}")

    with war_room_lock:
        report["computing"] = war_room_cache.get("computing", False)
        report["cache_ready"] = war_room_ready_fn(war_room_cache.get("data"))
        report["cache_age_sec"] = round(
            time.time() - (war_room_cache.get("ts") or 0), 1
        )

    return report
