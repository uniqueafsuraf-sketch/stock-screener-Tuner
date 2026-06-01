from __future__ import annotations

from screener.models import StockSnapshot


def _news_sentiment_score(news: list[dict]) -> float:
    if not news:
        return 0.0
    s = 0.0
    for n in news:
        sent = n.get("sentiment", "neutral")
        if sent == "bullish":
            s += 12
        elif sent == "bearish":
            s -= 8
        else:
            s += 2
    return min(20, max(-10, s))


def compute_edge_score(snap: StockSnapshot) -> float:
    """
    Proprietary 0–100 Edge Score — combines setup, flow, momentum, news, structure.
    Higher = more factors aligned for a discretionary trade idea.
    """
    score = 0.0

    # Technical setup conviction (from signal engine)
    score += min(35, snap.score * 4.5)

    # Relative volume — institutional participation
    if snap.volume_ratio >= 2.5:
        score += 18
    elif snap.volume_ratio >= 1.8:
        score += 12
    elif snap.volume_ratio >= 1.3:
        score += 6

    # RSI extremes
    if snap.rsi <= 32 and "SELLOFF" in snap.signals:
        score += 10
    elif snap.rsi >= 68 and snap.change_pct > 0:
        score += 5

    # Gap / extension
    if snap.gap_pct is not None:
        if snap.gap_pct >= 2 and "VOLUME_SPIKE" in snap.signals:
            score += 8
        elif snap.gap_pct <= -2 and "AT_SUPPORT" in snap.signals:
            score += 10

    # Outperforming market
    if snap.vs_spy_5d is not None:
        if snap.vs_spy_5d >= 3:
            score += 12
        elif snap.vs_spy_5d >= 1:
            score += 6
        elif snap.vs_spy_5d <= -3 and snap.rsi < 40:
            score += 5  # potential catch-up / bounce

    # 52-week positioning
    if snap.week52_position is not None:
        if snap.week52_position >= 0.95 and "BREAKOUT_SETUP" in snap.signals:
            score += 10
        elif snap.week52_position <= 0.2 and "AT_SUPPORT" in snap.signals:
            score += 8

    # Risk/reward from trendline distances
    if snap.risk_reward is not None and snap.risk_reward >= 2:
        score += min(12, snap.risk_reward * 3)

    # News catalyst
    score += _news_sentiment_score(snap.news)

    # High-conviction combo bonuses
    if "SELLOFF_AT_SUPPORT" in snap.signals:
        score += 12
    if "BREAKOUT_SETUP" in snap.signals:
        score += 10
    if "VOLUME_SPIKE" in snap.signals and snap.change_pct > 1.5:
        score += 8

    if snap.earnings_within_days is not None:
        if snap.earnings_within_days <= 3:
            score += 8
        elif snap.earnings_within_days <= 7:
            score += 5
        elif snap.earnings_within_days <= 14:
            score += 2

    return round(min(100, max(0, score)), 1)


def build_thesis(snap: StockSnapshot) -> str:
    """One-line actionable trade thesis."""
    parts: list[str] = []

    if "SELLOFF_AT_SUPPORT" in snap.signals:
        parts.append("Capitulation into support — watch for reversal confirmation and volume dry-up.")
    elif "BREAKOUT_SETUP" in snap.signals:
        parts.append("Volume expansion into resistance — breakout watch if price holds above trendline.")
    elif "VOLUME_SPIKE" in snap.signals:
        direction = "bullish continuation" if snap.change_pct > 0 else "distribution / flush"
        parts.append(f"Unusual volume ({snap.volume_ratio:.1f}× avg) suggests {direction}.")
    elif "SELLOFF" in snap.signals:
        parts.append(f"Sharp pullback ({snap.change_pct:.1f}%) on volume — mean-reversion or trend change.")
    elif "AT_SUPPORT" in snap.signals:
        parts.append("Price at rising support trendline — define stop below support for R/R.")
    elif "AT_RESISTANCE" in snap.signals:
        parts.append("Testing resistance trendline — fade or breakout depends on volume follow-through.")

    if snap.vs_spy_5d is not None and snap.vs_spy_5d >= 2:
        parts.append(f"Outperforming SPY by {snap.vs_spy_5d:.1f}% (5d) — relative strength leader.")
    elif snap.vs_spy_5d is not None and snap.vs_spy_5d <= -2:
        parts.append(f"Lagging SPY by {abs(snap.vs_spy_5d):.1f}% (5d) — potential laggard bounce if market firm.")

    if snap.gap_pct is not None and abs(snap.gap_pct) >= 1.5:
        parts.append(f"Gapped {snap.gap_pct:+.1f}% vs prior close — gap-fill or gap-and-go scenario.")

    if snap.earnings_within_days is not None and snap.earnings_within_days <= 14:
        parts.append(f"Earnings in {snap.earnings_within_days}d — reduce size or wait for report.")

    bullish_news = any(n.get("sentiment") == "bullish" for n in snap.news)
    if bullish_news:
        parts.append("Recent bullish headline flow — verify catalyst before entry.")

    if snap.risk_reward is not None and snap.risk_reward >= 2:
        parts.append(f"Estimated R/R ~{snap.risk_reward:.1f}:1 to resistance vs support.")

    if snap.unusual_activity:
        flags = ", ".join(a.replace("_", " ") for a in snap.unusual_activity[:3])
        parts.append(f"Unusual flow: {flags} (score {snap.unusual_score:.0f}).")

    if not parts:
        parts.append("Monitor for volume and trendline confirmation before sizing a position.")

    return " ".join(parts[:3])


def edge_grade(score: float) -> str:
    if score >= 75:
        return "A+"
    if score >= 65:
        return "A"
    if score >= 55:
        return "B+"
    if score >= 45:
        return "B"
    if score >= 35:
        return "C"
    return "—"
