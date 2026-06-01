from __future__ import annotations

import traceback
from datetime import datetime

from screener.gold_war_room.agents import (
    _trap_payload,
    agent_macro,
    agent_order_flow,
    agent_quant,
    agent_risk,
    agent_sentiment,
    agent_technical,
    agent_trap_detector,
    fake_breakout_panel,
    liquidity_sweep_panel,
    reversal_panel,
    smart_money_intent,
    stop_hunt_panel,
    trend_continuation_panel,
)
from screener.gold_war_room.fetch import (
    GoldMarketData,
    _synthetic_frames,
    build_chart_bundle,
    fetch_gold_data,
    fetch_gold_news,
)
from screener.gold_war_room.master import agent_consensus, build_alerts, run_master
from screener.gold_war_room.performance import (
    performance_summary,
    record_setup,
    record_war_room_cycle,
)
from screener.gold_war_room.scalping import analyze_scalping_setups


def _safe_agent(name: str, fn, *args) -> dict:
    try:
        out = fn(*args)
        if name == "trap" and "liquidity_sweep_up_prob" not in out:
            return _trap_payload(50, 50, 50, 50, 50, 50, 50, out.get("summary", "Trap detector incomplete."))
        return out
    except Exception as e:
        traceback.print_exc()
        if name == "trap":
            return _trap_payload(50, 50, 50, 50, 50, 50, 50, f"Agent paused: {e}")
        return {
            "id": name,
            "name": name.replace("_", " ").title(),
            "bullish_score": 50,
            "bearish_score": 50,
            "stance": "neutral",
            "summary": f"Agent paused: {e}",
            "error": str(e),
        }


def _build_response(
    data: GoldMarketData,
    agents: dict,
    trap: dict,
    risk: dict,
    master: dict,
    *,
    leverage: int = 30,
) -> dict:
    technical = agents["technical"]
    macro = agents["macro"]
    notes = " ".join(data.fetch_notes)
    why_extra = f" Data: {data.data_source}." if data.data_source not in ("live",) else ""
    return {
        "ok": True,
        "symbol": "XAUUSD (GC)",
        "price": data.price,
        "change_pct": data.change_pct,
        "price_symbol": "GC=F (COMEX)",
        "price_display": f"${data.price:,.2f}",
        "data_source": data.data_source,
        "fetch_notes": data.fetch_notes,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "market_bias": {
            "bias": master["market_bias"],
            "confidence": master["confidence_score"],
            "bull_probability": master["bull_probability"],
            "bear_probability": master["bear_probability"],
            "neutral_probability": master["neutral_probability"],
            "why": master["trade"]["why"] + why_extra + (" " + notes if notes else ""),
        },
        "confidence_meter": {
            "score": master["confidence_score"],
            "label": "High" if master["confidence_score"] > 75 else "Moderate" if master["confidence_score"] > 50 else "Low",
        },
        "agent_consensus": agent_consensus(agents, trap, risk),
        "agents": agents,
        "smart_money": {
            "title": "What Smart Money Likely Wants Next",
            "ranked": smart_money_intent(trap, technical, data.price),
        },
        "liquidity_sweep": liquidity_sweep_panel(trap, technical, data.price),
        "stop_hunt": stop_hunt_panel(trap),
        "fake_breakout": fake_breakout_panel(trap),
        "reversal": reversal_panel(trap, technical),
        "trend_continuation": trend_continuation_panel(trap, macro, technical),
        "trade_opportunity": master["trade"],
        "master": master,
        "alerts": build_alerts(trap),
        "performance": performance_summary(),
        "news": data.news or fetch_gold_news(),
        "chart": build_chart_bundle(
            data.frames,
            data.price,
            technical.get("key_levels"),
        ),
        "scalping": analyze_scalping_setups(
            data, agents, trap, technical, data.price, leverage=leverage,
        ),
        "live_scan": {
            "active": True,
            "interval_sec": 45,
            "agents_running": 7,
            "message": "Agents continuously re-scanning gold for scalp setups",
        },
    }


def run_war_room_analysis(*, leverage: int = 30) -> dict:
    try:
        data = fetch_gold_data()
        macro = _safe_agent("macro", agent_macro, data)
        technical = _safe_agent("technical", agent_technical, data)
        order_flow = _safe_agent("order_flow", agent_order_flow, data)
        sentiment = _safe_agent("sentiment", agent_sentiment, data)
        quant = _safe_agent("quant", agent_quant, data)
        primary = [macro, technical, order_flow, sentiment]
        risk = _safe_agent("risk", agent_risk, data, primary)
        trap = _safe_agent("trap", agent_trap_detector, data)

        agents = {
            "macro": macro,
            "technical": technical,
            "order_flow": order_flow,
            "sentiment": sentiment,
            "quant": quant,
            "risk": risk,
            "trap": trap,
        }

        master = run_master(agents, trap, risk, data.price, technical)
        payload = _build_response(data, agents, trap, risk, master, leverage=leverage)
        record_setup(master, data.price)
        record_war_room_cycle(payload)
        return payload
    except Exception as e:
        traceback.print_exc()
        try:
            data = GoldMarketData(
                price=2650.0,
                change_pct=0.0,
                frames=_synthetic_frames(),
                macro={},
                news=[],
                data_source="fallback",
                fetch_notes=[str(e)],
            )
            agents = {
                "macro": _safe_agent("macro", agent_macro, data),
                "technical": _safe_agent("technical", agent_technical, data),
                "order_flow": _safe_agent("order_flow", agent_order_flow, data),
                "sentiment": _safe_agent("sentiment", agent_sentiment, data),
                "quant": _safe_agent("quant", agent_quant, data),
            }
            primary = list(agents.values())[:4]
            risk = _safe_agent("risk", agent_risk, data, primary)
            trap = _safe_agent("trap", agent_trap_detector, data)
            agents["risk"] = risk
            agents["trap"] = trap
            master = run_master(agents, trap, risk, data.price, agents["technical"])
            payload = _build_response(data, agents, trap, risk, master, leverage=leverage)
            payload["ok"] = True
            payload["fetch_notes"] = [f"Recovered after error: {e}"]
            record_war_room_cycle(payload)
            return payload
        except Exception as e2:
            return {
                "ok": False,
                "error": f"{e}; recovery failed: {e2}",
                "agents": {},
                "market_bias": {"bias": "—", "confidence": 0, "why": str(e2)},
                "confidence_meter": {"score": 0, "label": "—"},
                "agent_consensus": {"rows": [], "headline": "—"},
                "smart_money": {"title": "What Smart Money Likely Wants Next", "ranked": []},
                "liquidity_sweep": {},
                "stop_hunt": {},
                "fake_breakout": {},
                "reversal": {},
                "trend_continuation": {},
                "trade_opportunity": {"status": "NO_HIGH_CONVICTION_TRADE", "why": str(e2)},
                "performance": performance_summary(),
                "alerts": [],
                "scalping": {"title": "Live Scalping Opportunities", "setups": [], "scanning": True},
                "live_scan": {"active": True, "interval_sec": 45, "agents_running": 7},
            }
