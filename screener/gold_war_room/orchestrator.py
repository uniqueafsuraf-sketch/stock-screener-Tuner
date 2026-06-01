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
from screener.gold_war_room.spot_consensus import fetch_consensus_spot
from screener.gold_war_room.master import agent_consensus, build_alerts, market_bias_display, run_master
from screener.gold_war_room.performance import (
    performance_summary,
    record_setup,
    record_war_room_cycle,
)
from screener.gold_war_room.scalping import analyze_scalping_setups
from screener.gold_war_room.stations import build_agent_stations


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
    live_spot: dict | None = None,
) -> dict:
    technical = agents["technical"]
    macro = agents["macro"]
    spot = live_spot or fetch_consensus_spot()
    display_price = spot.get("price") if spot.get("ok") else data.price
    display_chg = spot.get("change_pct") if spot.get("ok") else data.change_pct
    notes = " ".join(data.fetch_notes)
    bias_copy = market_bias_display(
        master["market_bias"],
        master["confidence_score"],
        master["bull_probability"],
        master["bear_probability"],
        bullish_agents=master["bullish_agents"],
        bearish_agents=master["bearish_agents"],
    )
    meaning = bias_copy["meaning"]
    if data.data_source not in ("live",):
        meaning += f" (Price data: {data.data_source}.)"
    if notes:
        meaning += f" {notes}"
    return {
        "ok": True,
        "symbol": "XAUUSD",
        "price": display_price,
        "change_pct": display_chg,
        "price_symbol": "XAUUSD spot",
        "price_display": f"${display_price:,.2f}" if display_price else "—",
        "live_spot": spot,
        "data_source": data.data_source,
        "fetch_notes": data.fetch_notes,
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "market_bias": {
            "bias": master["market_bias"],
            "headline": bias_copy["headline"],
            "meaning": meaning,
            "confidence": master["confidence_score"],
            "confidence_label": bias_copy["confidence_label"],
            "agents_summary": bias_copy["agents_summary"],
            "probability_detail": bias_copy["probability_detail"],
            "bull_probability": master["bull_probability"],
            "bear_probability": master["bear_probability"],
            "neutral_probability": master["neutral_probability"],
            "why": meaning,
        },
        "confidence_meter": {
            "score": master["confidence_score"],
            "label": bias_copy["confidence_label"],
        },
        "agent_consensus": agent_consensus(agents, trap, risk),
        "agent_stations": build_agent_stations(agents, trap, risk, data),
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
            display_price or data.price,
            technical.get("key_levels"),
        ),
        "scalping": analyze_scalping_setups(
            data,
            agents,
            trap,
            technical,
            display_price or data.price,
            leverage=leverage,
            live_spot=spot,
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

        live_spot = fetch_consensus_spot(force=True)
        spot_px = live_spot.get("price") if live_spot.get("ok") else data.price
        master = run_master(agents, trap, risk, spot_px, technical)
        payload = _build_response(
            data, agents, trap, risk, master, leverage=leverage, live_spot=live_spot,
        )
        record_setup(master, spot_px)
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
            live_spot = fetch_consensus_spot(force=True)
            spot_px = live_spot.get("price") if live_spot.get("ok") else data.price
            master = run_master(agents, trap, risk, spot_px, agents["technical"])
            payload = _build_response(
                data, agents, trap, risk, master, leverage=leverage, live_spot=live_spot,
            )
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
