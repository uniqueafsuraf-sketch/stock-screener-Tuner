from __future__ import annotations

import traceback
from datetime import datetime

from screener.gold_war_room.agents import (
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
from screener.gold_war_room.fetch import fetch_gold_data
from screener.gold_war_room.master import agent_consensus, build_alerts, run_master
from screener.gold_war_room.performance import performance_summary, record_setup


def run_war_room_analysis() -> dict:
    try:
        data = fetch_gold_data()
        macro = agent_macro(data)
        technical = agent_technical(data)
        order_flow = agent_order_flow(data)
        sentiment = agent_sentiment(data)
        primary = [macro, technical, order_flow, sentiment]
        risk = agent_risk(data, primary)
        quant = agent_quant(data)
        trap = agent_trap_detector(data)

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
        record_setup(master, data.price)

        return {
            "ok": True,
            "symbol": "XAUUSD (GC)",
            "price": data.price,
            "change_pct": data.change_pct,
            "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "market_bias": {
                "bias": master["market_bias"],
                "confidence": master["confidence_score"],
                "bull_probability": master["bull_probability"],
                "bear_probability": master["bear_probability"],
                "neutral_probability": master["neutral_probability"],
                "why": master["trade"]["why"],
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
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "ok": False,
            "error": str(e),
            "market_bias": {"bias": "—", "confidence": 0},
            "confidence_meter": {"score": 0, "label": "—"},
            "agent_consensus": {"rows": [], "headline": "—"},
            "smart_money": {"title": "", "ranked": []},
            "liquidity_sweep": {},
            "stop_hunt": {},
            "fake_breakout": {},
            "reversal": {},
            "trend_continuation": {},
            "trade_opportunity": {"status": "NO_HIGH_CONVICTION_TRADE"},
            "performance": performance_summary(),
            "alerts": [],
        }
