from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from screener.calendar_svc import attach_earnings, fetch_earnings_watch
from screener.data import avg_dollar_volume, fetch_batch, fetch_history
from screener.enrich import build_news_wire, enrich_all
from screener.features import augment_snapshot, build_scan_extras, spy_benchmark_change
from screener.market import fetch_market_pulse
from screener.models import ScanResult, StockSnapshot
from screener.signals import Opportunity, evaluate
from screener.universe import get_universe


def load_config(path: Path | str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_symbols(cfg: dict) -> list[str]:
    source = cfg.get("universe", "top_stocks")
    extra = cfg.get("watchlist", [])
    if source == "watchlist":
        return get_universe("watchlist", extra=extra or [])
    if source == "both_ourbit":
        return get_universe("both_ourbit", extra=extra)
    if source in ("both", "all"):
        return get_universe("all", extra=extra)
    if source == "ourbit":
        return get_universe("ourbit", extra=extra)
    if source == "etfs":
        return get_universe("etfs", extra=extra)
    return get_universe("top_stocks", extra=extra)


def _eval_cfg(cfg: dict) -> dict:
    return {
        "volume_spike_ratio": cfg["volume_spike_ratio"],
        "selloff_min_pct": cfg["selloff_min_pct"],
        "selloff_volume_ratio": cfg["selloff_volume_ratio"],
        "trendline_proximity_pct": cfg["trendline_proximity_pct"],
        "swing_window": cfg["swing_window"],
        "rsi_period": cfg["rsi_period"],
        "rsi_oversold": cfg["rsi_oversold"],
    }


def scan(config: dict | None = None, config_path: str = "config.yaml") -> list[Opportunity]:
    result = scan_full(config=config, config_path=config_path)
    return result.opportunities


def scan_full(
    config: dict | None = None,
    config_path: str = "config.yaml",
    use_batch: bool = True,
) -> ScanResult:
    cfg = config or load_config(config_path)
    symbols = resolve_symbols(cfg)
    eval_kw = _eval_cfg(cfg)
    min_dv = cfg["min_avg_dollar_volume"]
    lookback = cfg["lookback_days"]

    from screener.ourbit_universe import get_ourbit_lookup  # noqa: PLC0415

    ourbit_lookup = get_ourbit_lookup()

    def _tag_ourbit(snap: StockSnapshot) -> None:
        info = ourbit_lookup.get(snap.symbol.upper())
        if info:
            snap.on_ourbit = True
            snap.ourbit_symbol = info.get("ourbit_symbol", "")

    spy_df = fetch_history("SPY", min(lookback, 60))
    spy_5d = spy_benchmark_change(spy_df, 5)

    all_stocks: list[StockSnapshot] = []

    if use_batch and len(symbols) > 5:
        frames = fetch_batch(symbols, lookback)
    else:
        frames = {}
        for sym in symbols:
            df = fetch_history(sym, lookback)
            if df is not None:
                frames[sym] = df

    for symbol, df in frames.items():
        adv = avg_dollar_volume(df)
        if adv < min_dv:
            continue
        snap = evaluate(symbol, df, avg_dollar_volume_m=adv / 1_000_000, **eval_kw)
        snap = augment_snapshot(snap, df, spy_5d=spy_5d)
        _tag_ourbit(snap)
        all_stocks.append(snap)

    # Earnings — non-fatal if slow/fails
    earn_list: list[dict] = []
    try:
        top_for_cal = sorted(all_stocks, key=lambda s: -s.edge_score)[:25]
        earn_list = fetch_earnings_watch([s.symbol for s in top_for_cal], max_workers=6)
        attach_earnings({e["symbol"]: e["days"] for e in earn_list}, all_stocks)
    except Exception:
        pass

    opportunities = [s for s in all_stocks if s.has_opportunity]
    opportunities.sort(key=lambda o: (-o.edge_score, -o.score))
    all_stocks.sort(key=lambda s: (-s.unusual_score, -s.edge_score))

    news_cfg = cfg.get("news", {})
    wire_fetch = news_cfg.get("wire_fetch_for", news_cfg.get("fetch_for", "all"))
    enrich_all(
        all_stocks,
        max_news=news_cfg.get("max_headlines", 6),
        workers=news_cfg.get("workers", 12),
        only_opportunities=wire_fetch != "all",
        latest_first=True,
    )
    news_wire = build_news_wire(
        all_stocks,
        max_total=news_cfg.get("wire_max_total", 200),
    )

    from screener.edge import build_thesis, compute_edge_score, edge_grade

    for s in all_stocks:
        s.edge_score = compute_edge_score(s)
        s.edge_grade = edge_grade(s.edge_score)
        s.thesis = build_thesis(s)

    extras = build_scan_extras(all_stocks, cfg)
    try:
        pulse = fetch_market_pulse()
    except Exception:
        pulse = []

    unusual_count = len(extras["unusual_activity"])
    stats = {
        "total_opportunities": len(opportunities),
        "edge_a_plus": sum(1 for s in all_stocks if s.edge_score >= 75),
        "edge_a": sum(1 for s in all_stocks if s.edge_score >= 65),
        "unusual_active": unusual_count,
        "volume_spikes": sum(1 for s in opportunities if "VOLUME_SPIKE" in s.signals),
        "selloffs": sum(1 for s in opportunities if "SELLOFF" in s.signals),
        "at_support": sum(1 for s in opportunities if "AT_SUPPORT" in s.signals),
        "breakout_setups": sum(1 for s in opportunities if "BREAKOUT_SETUP" in s.signals),
        "bullish_news": sum(1 for s in all_stocks if any(n.get("sentiment") == "bullish" for n in s.news)),
        "gaps_today": len(extras["gaps"]),
        "earnings_soon": len(earn_list),
        "gainers": sum(1 for s in all_stocks if s.change_pct > 0),
        "losers": sum(1 for s in all_stocks if s.change_pct < 0),
        "ourbit_count": sum(1 for s in all_stocks if s.on_ourbit),
    }

    return ScanResult(
        scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        symbols_scanned=len(all_stocks),
        opportunities=opportunities,
        all_stocks=all_stocks,
        stats=stats,
        edge_plays=extras["edge_plays"],
        gainers=extras["gainers"],
        losers=extras["losers"],
        gaps=extras["gaps"],
        high_rvol=extras["high_rvol"],
        rel_strength=extras["rel_strength"],
        unusual_activity=extras["unusual_activity"],
        earnings_watch=earn_list,
        market_pulse=pulse,
        proprietary_signals=extras["proprietary_signals"],
        news_wire=news_wire,
    )
