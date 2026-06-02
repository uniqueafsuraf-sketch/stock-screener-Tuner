#!/usr/bin/env python3
"""Local web dashboard — reliable loading with live bootstrap + scan cache."""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from screener.alerts import create_alert, delete_alert, evaluate_alerts, load_alerts  # noqa: E402
from screener.cache_io import (  # noqa: E402
    load_scan_cache,
    load_seed_bootstrap,
    load_war_room_seed,
    save_scan_cache,
    save_war_room_seed,
)
from screener.runtime import is_cloud_host  # noqa: E402
from screener.live import LiveEngine  # noqa: E402
from screener.scan import load_config, resolve_symbols, scan_full  # noqa: E402

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

CONFIG_PATH = ROOT / "config.yaml"
_scan_cache: dict = {"data": None, "ts": 0.0, "scanning": False, "last_error": None}
_scan_lock = threading.Lock()
_live_engine: LiveEngine | None = None
_bg_started = False
_bg_scheduled = False
_alert_history: list[dict] = []
_alert_lock = threading.Lock()
_pulse_cache: dict = {"data": [], "ts": 0.0}
_OURBIT_PAYLOAD_VERSION = 2
_ROW_LIST_KEYS = (
    "opportunities", "all_stocks", "edge_plays", "gainers", "losers",
    "gaps", "high_rvol", "rel_strength", "unusual_activity", "ourbit_stocks",
)


def _cfg() -> dict:
    cfg = load_config(CONFIG_PATH)
    if is_cloud_host():
        live = dict(cfg.get("live") or {})
        live["interval_sec"] = max(float(live.get("interval_sec", 1)), 3.0)
        live["full_scan_interval_sec"] = max(int(live.get("full_scan_interval_sec", 300)), 600)
        news = dict(cfg.get("news") or {})
        news["wire_fetch_for"] = "opportunities"
        news["workers"] = min(int(news.get("workers", 12)), 4)
        cfg = {
            **cfg,
            "universe": cfg.get("universe", "both_ourbit"),
            "live": live,
            "news": news,
        }
    return cfg


def _live_cfg() -> dict:
    return _cfg().get("live", {})


def _ourbit_sync_interval() -> int:
    return int(_cfg().get("ourbit", {}).get("sync_interval_sec", 900))


def _congress_sync_interval() -> int:
    return int(_cfg().get("congress", {}).get("sync_interval_sec", 3600))


def _congress_sync_loop() -> None:
    """Refresh STOCK Act disclosure cache in the background."""
    time.sleep(90)
    while True:
        try:
            from screener.congress_trades import build_congress_payload, save_congress_cache  # noqa: PLC0415

            payload = build_congress_payload(lookback_days=180)
            if payload.get("ok"):
                save_congress_cache(payload)
                print(
                    f"Congress trades refreshed: {payload.get('total_trades')} filings, "
                    f"{(payload.get('stats') or {}).get('recent_buy_count', 0)} recent buys"
                )
        except Exception as e:
            print(f"Congress sync failed: {e}")
        time.sleep(_congress_sync_interval())


def _ourbit_sync_loop() -> None:
    """Poll Ourbit for new tokenized stock listings; rescan when new tickers appear."""
    time.sleep(60)
    while True:
        try:
            from screener.ourbit_universe import sync_ourbit_stocks  # noqa: PLC0415

            result = sync_ourbit_stocks(refresh=True)
            new = result.get("new_tickers") or []
            if new:
                print(f"Ourbit: {len(new)} new stock listing(s): {', '.join(new)}")
                _run_scan(force=True)
        except Exception as e:
            print(f"Ourbit sync failed: {e}")
        time.sleep(_ourbit_sync_interval())


def _scan_interval() -> int:
    return int(_live_cfg().get("full_scan_interval_sec", 300))


def _json_safe(obj):
    """Ensure Flask jsonify won't fail on numpy types."""
    return json.loads(json.dumps(obj, default=str))


def _default_chart_links(sym: str) -> dict:
    return {
        "tradingview": f"https://www.tradingview.com/chart/?symbol={sym}",
        "yahoo": f"https://finance.yahoo.com/quote/{sym}/chart/",
        "finviz": f"https://finviz.com/quote.ashx?t={sym}",
        "yahoo_news": f"https://finance.yahoo.com/quote/{sym}/news/",
    }


def _tag_row_ourbit(row: dict, lookup: dict[str, dict]) -> dict:
    out = dict(row)
    sym = (out.get("symbol") or "").upper().strip()
    info = lookup.get(sym)
    if info:
        out["on_ourbit"] = True
        out["ourbit_symbol"] = info.get("ourbit_symbol", "")
    else:
        out.setdefault("on_ourbit", False)
        out.setdefault("ourbit_symbol", "")
    return out


def _minimal_ourbit_row(ticker: str, info: dict) -> dict:
    return {
        "symbol": ticker,
        "price": 0.0,
        "change_pct": 0.0,
        "volume_ratio": 0.0,
        "rsi": 50.0,
        "score": 0,
        "edge_score": 0.0,
        "edge_grade": "—",
        "signals": [],
        "notes": [],
        "news": [],
        "thesis": "Ourbit-listed — full scan loading…",
        "unusual_activity": [],
        "unusual_score": 0.0,
        "dollar_volume_m": 0,
        "chart_links": _default_chart_links(ticker),
        "live": False,
        "has_opportunity": False,
        "on_ourbit": True,
        "ourbit_symbol": info.get("ourbit_symbol", ""),
    }


def _apply_ourbit_payload(data: dict, *, live_quotes: dict | None = None) -> dict:
    """Tag rows with Ourbit metadata and build a dedicated ourbit_stocks list."""
    from screener.ourbit_universe import get_ourbit_lookup  # noqa: PLC0415

    lookup = get_ourbit_lookup(allow_fetch=False)
    if not lookup:
        return data

    out = dict(data)
    for key in _ROW_LIST_KEYS:
        if key in out and isinstance(out[key], list):
            out[key] = [_tag_row_ourbit(r, lookup) for r in out[key] if isinstance(r, dict)]

    by_sym: dict[str, dict] = {}
    for row in out.get("all_stocks") or []:
        sym = (row.get("symbol") or "").upper().strip()
        if sym:
            by_sym[sym] = row

    quotes = live_quotes or {}
    ourbit_stocks: list[dict] = []
    for ticker, info in sorted(lookup.items()):
        row = by_sym.get(ticker)
        if row:
            row = _tag_row_ourbit(row, lookup)
        elif quotes.get(ticker):
            row = _tag_row_ourbit(_stock_from_quote(ticker, quotes[ticker]), lookup)
        else:
            row = _minimal_ourbit_row(ticker, info)
        ourbit_stocks.append(row)

    out["ourbit_stocks"] = ourbit_stocks
    out["ourbit_listed"] = len(lookup)
    stats = dict(out.get("stats") or {})
    stats["ourbit_count"] = len(ourbit_stocks)
    out["stats"] = stats
    out["ourbit_payload_version"] = _OURBIT_PAYLOAD_VERSION

    # Every Ourbit ticker must appear in Full universe (all_stocks), not only the Ourbit tab.
    merged_all = list(out.get("all_stocks") or [])
    seen_syms = {(r.get("symbol") or "").upper() for r in merged_all if isinstance(r, dict)}
    for row in ourbit_stocks:
        sym = (row.get("symbol") or "").upper()
        if sym and sym not in seen_syms:
            merged_all.append(row)
            seen_syms.add(sym)
    merged_all.sort(key=lambda r: (r.get("symbol") or ""))
    out["all_stocks"] = merged_all
    return out


def _apply_congress_payload(data: dict) -> dict:
    """Tag scan rows with STOCK Act politician purchase data and attach congress feed."""
    try:
        from screener.congress_trades import (  # noqa: PLC0415
            get_congress_payload,
            get_congress_lookup,
            tag_row_with_congress,
        )
    except Exception:
        traceback.print_exc()
        return data

    lookup = get_congress_lookup(refresh=False)
    if not lookup:
        return data

    out = dict(data)
    for key in _ROW_LIST_KEYS:
        if key in out and isinstance(out[key], list):
            out[key] = [
                tag_row_with_congress(r, lookup) for r in out[key] if isinstance(r, dict)
            ]

    payload = get_congress_payload(refresh=False)
    out["congress_trades"] = {
        "recent_buys": (payload.get("recent_buys") or [])[:60],
        "edge_leaders": (payload.get("edge_leaders") or [])[:30],
        "stats": payload.get("stats") or {},
        "fetched_at": payload.get("fetched_at"),
        "source": payload.get("source"),
        "sources_active": payload.get("sources_active") or [],
        "min_buy_usd": payload.get("min_buy_usd") or 5000,
        "stale": payload.get("stale", False),
    }
    stats = dict(out.get("stats") or {})
    cstats = payload.get("stats") or {}
    stats["congress_buys"] = cstats.get("recent_buy_count", 0)
    stats["congress_symbols"] = cstats.get("symbols_with_buys", 0)
    out["stats"] = stats
    return out


def _enrich_hub_payload(data: dict, *, live_quotes: dict | None = None) -> dict:
    data = _apply_ourbit_payload(data, live_quotes=live_quotes)
    return _apply_congress_payload(data)


def _stock_from_quote(sym: str, q: dict) -> dict:
    chg = float(q.get("change_pct") or 0)
    vol = float(q.get("volume_ratio") or 0)
    row = {
        "symbol": sym,
        "price": float(q.get("price") or 0),
        "change_pct": chg,
        "volume_ratio": vol,
        "rsi": 50.0,
        "score": 0,
        "edge_score": min(100, round(vol * 15 + abs(chg) * 3, 1)),
        "edge_grade": "—",
        "signals": [],
        "notes": [],
        "news": [],
        "thesis": "Live quote — full scan loading…",
        "unusual_activity": ["ELEVATED_VOLUME"] if vol >= 1.8 else [],
        "unusual_score": min(100, round(vol * 20 + abs(chg) * 2, 1)),
        "dollar_volume_m": 0,
        "chart_links": _default_chart_links(sym),
        "live": True,
        "has_opportunity": False,
        "on_ourbit": False,
        "ourbit_symbol": "",
    }
    from screener.ourbit_universe import get_ourbit_lookup  # noqa: PLC0415

    info = get_ourbit_lookup().get(sym.upper())
    if info:
        row["on_ourbit"] = True
        row["ourbit_symbol"] = info.get("ourbit_symbol", "")
    return row


def _bootstrap_from_live() -> dict:
    """Instant table data from live quotes while full scan runs."""
    engine = _ensure_background()
    live = engine.get_payload()
    quotes = live.get("quotes", {})

    if not quotes:
        return {
            "ok": True,
            "scanning": True,
            "scanned_at": "",
            "symbols_scanned": 0,
            "universe_size": len(resolve_symbols(_cfg())),
            "opportunities": [],
            "all_stocks": [],
            "edge_plays": [],
            "unusual_activity": [],
            "gainers": [],
            "losers": [],
            "gaps": [],
            "high_rvol": [],
            "rel_strength": [],
            "earnings_watch": [],
            "market_pulse": _get_market_pulse(),
            "stats": {},
            "proprietary_signals": [],
            "live": live,
            "message": "Fetching live quotes…",
        }

    stocks = [_stock_from_quote(sym, q) for sym, q in quotes.items()]
    stocks.sort(key=lambda s: (-s["unusual_score"], -abs(s["change_pct"])))
    unusual = [s for s in stocks if s["unusual_score"] >= 20][:30]
    gainers = sorted(stocks, key=lambda s: -s["change_pct"])[:15]
    losers = sorted(stocks, key=lambda s: s["change_pct"])[:15]

    return {
        "ok": True,
        "scanning": _scan_cache.get("scanning", True),
        "scanned_at": "",
        "symbols_scanned": len(stocks),
        "universe_size": len(resolve_symbols(_cfg())),
        "opportunities": [],
        "all_stocks": stocks,
        "edge_plays": stocks[:25],
        "unusual_activity": unusual,
        "gainers": gainers,
        "losers": losers,
        "gaps": [],
        "high_rvol": sorted(stocks, key=lambda s: -s["volume_ratio"])[:15],
        "rel_strength": [],
        "earnings_watch": [],
        "market_pulse": _get_market_pulse(),
        "stats": {
            "unusual_active": len(unusual),
            "gainers": sum(1 for s in stocks if s["change_pct"] > 0),
        },
        "proprietary_signals": [],
        "live": live,
        "message": "Live mode — full scan running in background",
    }


def _build_movers_tape(*, start_bg: bool = True) -> list[dict]:
    """Top gainers / losers by change % only (for header ticker)."""
    from screener.movers import movers_tape_list

    quotes: dict = {}
    if start_bg:
        engine = _ensure_background()
        quotes = engine.get_payload().get("quotes", {}) or {}
    elif _live_engine is not None:
        quotes = _live_engine.get_payload().get("quotes", {}) or {}

    with _scan_lock:
        cached = _scan_cache.get("data") or {}

    stocks = cached.get("all_stocks") or []
    return movers_tape_list(stocks, quotes, top_n=15)


def _get_market_pulse(*, start_bg: bool = True) -> list:
    pulse = _build_movers_tape(start_bg=start_bg)
    if pulse:
        _pulse_cache["data"] = pulse
        _pulse_cache["ts"] = time.time()
    return pulse or _pulse_cache["data"] or []


def _load_disk_cache_into_memory() -> None:
    disk = load_scan_cache()
    src = "cache"
    if not disk:
        disk = load_seed_bootstrap()
        src = "seed"
    if disk:
        stale_ourbit = (
            disk.get("ourbit_payload_version") != _OURBIT_PAYLOAD_VERSION
            or "ourbit_stocks" not in disk
        )
        disk = _enrich_hub_payload(disk)
        with _scan_lock:
            cur = _scan_cache.get("data")
            empty = not (cur and cur.get("all_stocks"))
            if cur is None or empty:
                _scan_cache["data"] = disk
                _scan_cache["ts"] = time.time()
                n_ob = len(disk.get("ourbit_stocks") or [])
                print(f"Loaded {len(disk.get('all_stocks', []))} stocks from {src} ({n_ob} Ourbit)")
                if stale_ourbit and is_cloud_host():
                    threading.Thread(
                        target=lambda: _run_scan(force=True),
                        daemon=True,
                        name="ourbit-cache-refresh",
                    ).start()


def _ensure_background() -> LiveEngine:
    global _live_engine, _bg_started
    if _live_engine is None:
        interval = float(_live_cfg().get("interval_sec", 1))
        if is_cloud_host():
            interval = max(interval, 2.0)
        _live_engine = LiveEngine(interval_sec=interval)

    if not _bg_started:
        _bg_started = True
        _load_disk_cache_into_memory()
        symbols = list(resolve_symbols(_cfg()))
        with _scan_lock:
            cached = _scan_cache.get("data") or {}
            for row in cached.get("all_stocks") or []:
                sym = (row.get("symbol") or "").upper().strip()
                if sym and sym not in symbols:
                    symbols.append(sym)
        _live_engine.set_symbols(symbols)
        if _live_cfg().get("enabled", True):
            _live_engine.start()
        threading.Thread(target=_scan_loop, daemon=True, name="scan-loop").start()
        threading.Thread(target=_ourbit_sync_loop, daemon=True, name="ourbit-sync").start()
        threading.Thread(target=_congress_sync_loop, daemon=True, name="congress-sync").start()
        def _initial_scan() -> None:
            if is_cloud_host():
                time.sleep(25)
            _run_scan(force=True)

        threading.Thread(target=_initial_scan, daemon=True, name="initial-scan").start()

    return _live_engine


def _patch_row_with_quote(row: dict, quote: dict | None) -> dict:
    if not quote:
        return row
    row = dict(row)
    if quote.get("price") is not None:
        row["price"] = quote["price"]
    if quote.get("change_pct") is not None:
        row["change_pct"] = quote["change_pct"]
    if quote.get("volume_ratio") is not None:
        row["volume_ratio"] = quote["volume_ratio"]
    row["live"] = True
    return row


def _live_payload_safe() -> dict:
    if _live_engine is None:
        return {"quotes": {}, "count": 0, "fetching": True, "updated_at": "", "tick": 0, "error": None}
    try:
        return _live_engine.get_payload()
    except Exception:
        return {"quotes": {}, "count": 0, "fetching": False, "error": "live unavailable"}


def _merge_scan_with_live(scan_data: dict, *, start_bg: bool = True) -> dict:
    if start_bg:
        _schedule_background_start()
    live = _live_payload_safe()
    quotes = live.get("quotes", {})

    data = dict(scan_data)
    for key in (
        "opportunities", "all_stocks", "edge_plays", "gainers", "losers",
        "gaps", "high_rvol", "rel_strength", "unusual_activity",
    ):
        if key in data and isinstance(data[key], list):
            data[key] = [
                _patch_row_with_quote(r, quotes.get(r.get("symbol", "")))
                for r in data[key]
            ]

    if not data.get("all_stocks") and quotes:
        boot = _bootstrap_from_live()
        data.update(boot)

    data["market_pulse"] = _get_market_pulse(start_bg=start_bg)
    data["live"] = live
    data["alerts"] = load_alerts().to_dict()
    with _alert_lock:
        data["alert_feed"] = list(_alert_history)
    if _scan_cache.get("last_error"):
        data["last_error"] = _scan_cache["last_error"]
    data["scanning"] = _scan_cache.get("scanning", False)
    return _enrich_hub_payload(data, live_quotes=quotes)


def _run_scan(force: bool = False) -> None:
    with _scan_lock:
        if _scan_cache["scanning"] and not force:
            return
        _scan_cache["scanning"] = True
        _scan_cache["last_error"] = None

    print("Starting full market scan…")
    try:
        from screener.ourbit_universe import get_ourbit_lookup  # noqa: PLC0415

        cfg = _cfg()
        result = scan_full(config=cfg, use_batch=True)
        payload = {
            **result.to_dict(),
            "ok": True,
            "scanning": False,
            "universe_size": len(resolve_symbols(cfg)),
            "ourbit_listed": len(get_ourbit_lookup()),
        }
        save_scan_cache(payload)
        with _scan_lock:
            _scan_cache["data"] = payload
            _scan_cache["ts"] = time.time()
            _scan_cache["scanning"] = False
            _scan_cache["last_error"] = None

        syms = [s["symbol"] for s in payload.get("all_stocks", [])]
        if syms:
            _ensure_background().set_symbols(syms)
        print(f"Scan complete: {len(syms)} stocks")
    except Exception as e:
        traceback.print_exc()
        with _scan_lock:
            _scan_cache["scanning"] = False
            _scan_cache["last_error"] = str(e)
        print(f"Scan failed: {e}")


def _scan_loop() -> None:
    while True:
        time.sleep(_scan_interval())
        _run_scan(force=True)


def _scan_response(force: bool = False) -> dict:
    _schedule_background_start()
    with _scan_lock:
        has_stocks = bool((_scan_cache.get("data") or {}).get("all_stocks"))
    if not has_stocks:
        _load_disk_cache_into_memory()

    if force:
        with _scan_lock:
            already = _scan_cache["scanning"]
        if not already:
            threading.Thread(target=lambda: _run_scan(force=True), daemon=True).start()

    with _scan_lock:
        cached = _scan_cache["data"]
        scanning = _scan_cache["scanning"]

    if cached and cached.get("all_stocks"):
        if force:
            merged = _merge_scan_with_live(cached)
            merged["ok"] = True
            merged["scanning"] = scanning
            return merged
        data = dict(cached)
        data["ok"] = True
        data["scanning"] = scanning
        data["live"] = _live_payload_safe()
        if _scan_cache.get("last_error"):
            data["last_error"] = _scan_cache["last_error"]
        return data

    # No full scan yet — return live bootstrap immediately
    boot = _bootstrap_from_live()
    boot["scanning"] = scanning or not boot.get("all_stocks")
    return _merge_scan_with_live(boot)


@app.route("/")
def index():
    from dashboard.launch import APP_VERSION  # noqa: PLC0415

    return render_template("index.html", app_version=APP_VERSION)


def _slim_hub_payload(data: dict) -> dict:
    """Trim heavy news fields for fast hub first paint (keeps all stock rows)."""
    out = dict(data)
    wire = out.get("news_wire")
    if isinstance(wire, list) and len(wire) > 100:
        out["news_wire"] = wire[:100]
    for key in _ROW_LIST_KEYS:
        rows = out.get(key)
        if not isinstance(rows, list):
            continue
        slim: list = []
        for row in rows:
            if not isinstance(row, dict):
                slim.append(row)
                continue
            r = dict(row)
            news = r.get("news")
            if isinstance(news, list) and len(news) > 2:
                r["news"] = news[:2]
            slim.append(r)
        out[key] = slim
    return out


_war_room_cache: dict = {
    "data": None,
    "ts": 0.0,
    "computing": False,
    "computing_since": 0.0,
    "ctx": None,
    "leverage": 100,
}
_war_room_lock = threading.Lock()
WAR_ROOM_TTL = 45
WAR_ROOM_SCAN_INTERVAL = 90 if is_cloud_host() else 45
WAR_ROOM_RESOLVE_INTERVAL = 60 if is_cloud_host() else 30
WAR_ROOM_COMPUTE_MAX = 75
_war_room_heavy_lock = threading.Lock()
_war_room_watchdog_started = False
_last_spot_for_resolve: dict = {"price": None, "ts": 0.0}


def _war_room_ready(cached: dict | None) -> bool:
    return bool(cached and cached.get("ok") and not cached.get("warming") and cached.get("agents"))


def _load_war_room_seed_into_cache() -> bool:
    seed = load_war_room_seed()
    if not seed:
        return False
    with _war_room_lock:
        _war_room_cache["data"] = seed
        _war_room_cache["ts"] = time.time()
        _war_room_cache["computing"] = False
    print(f"Loaded Gold War Room seed ({len(seed.get('agents', {}))} agents)")
    return True


def _war_room_warming_payload() -> dict:
    return {
        "ok": True,
        "warming": True,
        "message": "Agents analyzing gold — results in a few seconds…",
        "symbol": "XAUUSD",
        "price_symbol": "XAUUSD spot",
        "market_bias": {
            "bias": "—",
            "headline": "Analyzing gold…",
            "meaning": "Agents are scanning — bias will appear in a few seconds.",
            "confidence": 0,
            "confidence_label": "—",
            "why": "Analysis in progress…",
        },
        "confidence_meter": {"score": 0, "label": "—"},
        "agent_consensus": {"rows": [], "headline": "Analyzing…"},
        "agents": {},
        "smart_money": {"title": "What Smart Money Likely Wants Next", "ranked": []},
        "liquidity_sweep": {},
        "stop_hunt": {},
        "fake_breakout": {},
        "reversal": {},
        "trend_continuation": {},
        "trade_opportunity": {"status": "NO_HIGH_CONVICTION_TRADE", "why": "Waiting for agent consensus…"},
        "performance": {"total_setups": 0, "win_rate": 0, "loss_rate": 0, "average_rr": 0},
        "alerts": [],
        "news": [],
        "chart": {"symbol": "XAUUSD", "tv_symbol": "OANDA:XAUUSD", "candles": [], "interval": "1H"},
        "scalping": {"title": "Live Scalping Opportunities", "setups": [], "scanning": True},
        "live_scan": {"active": True, "interval_sec": 45, "agents_running": 7},
        "agent_stations": {
            "title": "Agent Operations Center",
            "stations": [],
            "overseers": [],
            "crew": [],
            "map_rooms": [],
            "headline": "Analyzing…",
            "floor_status": "Starting agents…",
        },
    }


def _reset_war_room_compute_lock() -> None:
    with _war_room_lock:
        _war_room_cache["computing"] = False
        _war_room_cache["computing_since"] = 0.0


def _refresh_war_room_async(*, force: bool = False) -> None:
    with _war_room_lock:
        if _war_room_cache.get("computing"):
            started = _war_room_cache.get("computing_since") or 0.0
            if time.time() - started < WAR_ROOM_COMPUTE_MAX:
                return
        _war_room_cache["computing"] = True
        _war_room_cache["computing_since"] = time.time()

    def _run() -> None:
        from screener.gold_war_room import run_war_room_analysis  # noqa: PLC0415

        if not _war_room_heavy_lock.acquire(blocking=False):
            _reset_war_room_compute_lock()
            return
        try:
            ctx_holder: dict = {}
            with _war_room_lock:
                lev = int(_war_room_cache.get("leverage") or 100)
            payload = run_war_room_analysis(
                leverage=max(10, min(200, lev)),
                ctx_out=ctx_holder,
            )
            if payload.get("ok"):
                save_war_room_seed(payload)
            with _war_room_lock:
                _war_room_cache["data"] = payload
                _war_room_cache["ts"] = time.time()
                _war_room_cache["ctx"] = ctx_holder if ctx_holder else None
        except Exception as e:
            traceback.print_exc()
            with _war_room_lock:
                err_payload = _war_room_warming_payload()
                err_payload["ok"] = False
                err_payload["error"] = str(e)
                _war_room_cache["data"] = err_payload
                _war_room_cache["ts"] = time.time()
        finally:
            _reset_war_room_compute_lock()
            _war_room_heavy_lock.release()

    threading.Thread(target=_run, daemon=True, name="war-room-refresh").start()


_WAR_ROOM_PAGE_BOOTSTRAP: dict = {
    "ok": True,
    "warming": True,
    "message": "Loading desk via API…",
    "market_bias": {"headline": "Loading…", "meaning": "Agents connect in a few seconds."},
    "confidence_meter": {"score": 0, "label": "—"},
    "agents": {},
    "agent_consensus": {"rows": [], "headline": "—"},
    "news": [],
}


@app.route("/gold-war-room")
def gold_war_room_page():
    from dashboard.brand import SITE_NAME  # noqa: PLC0415
    from dashboard.launch import APP_VERSION  # noqa: PLC0415

    try:
        return render_template(
            "gold_war_room.html",
            site_name=SITE_NAME,
            app_version=APP_VERSION,
            initial=_WAR_ROOM_PAGE_BOOTSTRAP,
        )
    except Exception as e:
        traceback.print_exc()
        return render_template(
            "gold_war_room.html",
            site_name=SITE_NAME,
            app_version=APP_VERSION,
            initial={
                "ok": True,
                "error": str(e),
                "market_bias": {"headline": "War Room recovering", "meaning": "Reload in a few seconds."},
            },
        ), 200


def _war_room_leverage() -> int:
    with _war_room_lock:
        return max(10, min(200, int(_war_room_cache.get("leverage") or 100)))


def _patch_cached_scalping_for_leverage(cached: dict, leverage: int) -> dict:
    from screener.gold_war_room.orchestrator import patch_payload_scalping  # noqa: PLC0415

    with _war_room_lock:
        ctx = _war_room_cache.get("ctx")
    return patch_payload_scalping(cached, leverage, ctx)


@app.route("/api/gold-war-room/scalp")
def api_gold_war_room_scalp():
    """Fast scalp desk update when leverage changes (no full agent re-run)."""
    from screener.gold_war_room.orchestrator import patch_payload_scalping  # noqa: PLC0415

    lev_arg = request.args.get("leverage", type=int)
    if lev_arg is None:
        lev_arg = _war_room_leverage()
    lev = max(10, min(200, int(lev_arg)))
    with _war_room_lock:
        _war_room_cache["leverage"] = lev
        cached = _war_room_cache.get("data")
        ctx = _war_room_cache.get("ctx")

    if not _war_room_ready(cached):
        return jsonify({
            "ok": False,
            "error": "War room still loading — wait a few seconds",
            "scalping": {"setups": [], "scanning": True},
        })

    try:
        patched = patch_payload_scalping(dict(cached), lev, ctx)
        scalping = patched.get("scalping") or {}
        callout = patched.get("leverage_callout") or scalping.get("leverage_callout") or ""
        with _war_room_lock:
            if _war_room_cache.get("data"):
                data = dict(_war_room_cache["data"])
                data["scalping"] = scalping
                data["leverage_callout"] = callout
                _war_room_cache["data"] = data
        return jsonify(_json_safe({
            "ok": True,
            "leverage": lev,
            "scalping": scalping,
            "callout": callout,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e), "scalping": cached.get("scalping", {})})


def _war_room_api_payload(payload: dict) -> dict:
    """Strip chart candles for faster JSON (client uses TradingView embed)."""
    out = dict(payload)
    chart = dict(out.get("chart") or {})
    chart["candles"] = []
    out["chart"] = chart
    return out


@app.route("/api/gold-war-room/ping")
def api_gold_war_room_ping():
    with _war_room_lock:
        ready = _war_room_ready(_war_room_cache.get("data"))
        computing = bool(_war_room_cache.get("computing"))
    return jsonify({"ok": True, "ready": ready, "computing": computing})


@app.route("/api/gold-war-room/bootstrap")
def api_gold_war_room_bootstrap():
    """Instant desk JSON from bundled seed (never blocks on agent run)."""
    with _war_room_lock:
        cached = _war_room_cache.get("data")
    if _war_room_ready(cached):
        return jsonify(_json_safe(_war_room_api_payload(cached)))
    seed = load_war_room_seed()
    if seed and seed.get("ok"):
        with _war_room_lock:
            _war_room_cache["data"] = seed
            _war_room_cache["ts"] = time.time()
            _war_room_cache["computing"] = False
        return jsonify(_json_safe(_war_room_api_payload(seed)))
    return jsonify(_json_safe(_war_room_warming_payload()))


@app.route("/api/gold-war-room")
def api_gold_war_room():
    try:
        force = request.args.get("refresh") == "1"
        lev_only = request.args.get("leverage_only") == "1"
        lev_arg = request.args.get("leverage", type=int)
        if lev_arg is not None and lev_only:
            with _war_room_lock:
                _war_room_cache["leverage"] = max(10, min(200, lev_arg))
        now = time.time()
        with _war_room_lock:
            cached = _war_room_cache.get("data")
            age = now - (_war_room_cache.get("ts") or 0)
            computing = _war_room_cache.get("computing", False)
            started = _war_room_cache.get("computing_since") or 0.0
            requested_lev = _war_room_leverage()

        if computing and started and (now - started) > WAR_ROOM_COMPUTE_MAX:
            _reset_war_room_compute_lock()
            computing = False

        if _war_room_ready(cached) and lev_only and lev_arg is not None:
            try:
                patched = _patch_cached_scalping_for_leverage(cached, requested_lev)
                with _war_room_lock:
                    _war_room_cache["data"] = patched
                return jsonify(_json_safe(_war_room_api_payload(patched)))
            except Exception:
                traceback.print_exc()

        if _war_room_ready(cached) and not force:
            return jsonify(_json_safe(_war_room_api_payload(cached)))

        if not computing and force and not is_cloud_host():
            _refresh_war_room_async(force=True)

        if _war_room_ready(cached):
            out = dict(cached)
            if force or age >= WAR_ROOM_TTL:
                out["stale"] = True
            return jsonify(_json_safe(_war_room_api_payload(out)))

        warm = _war_room_warming_payload()
        return jsonify(_json_safe(warm))
    except Exception as e:
        traceback.print_exc()
        out = _war_room_warming_payload()
        out["ok"] = False
        out["error"] = str(e)
        return jsonify(_json_safe(out))


def _schedule_async_resolve() -> None:
    """Resolve trades in background — never block HTTP (prevents 502 on Render)."""
    def _run() -> None:
        if not _war_room_heavy_lock.acquire(blocking=False):
            return
        try:
            from screener.gold_war_room.performance import resolve_open_trades  # noqa: PLC0415

            px = _cached_spot_price()
            if px is not None:
                resolve_open_trades(px)
        except Exception as e:
            print(f"Async resolve: {e}")
        finally:
            try:
                _war_room_heavy_lock.release()
            except RuntimeError:
                pass

    threading.Thread(target=_run, daemon=True, name="war-room-resolve-async").start()


def _cached_spot_price(*, max_age: float = 25.0) -> float | None:
    now = time.time()
    if (now - (_last_spot_for_resolve.get("ts") or 0)) < max_age:
        return _last_spot_for_resolve.get("price")
    try:
        from screener.gold_war_room.fetch import fetch_spot_payload  # noqa: PLC0415

        spot = fetch_spot_payload()
        if spot.get("ok") and spot.get("price") is not None:
            _last_spot_for_resolve["price"] = float(spot["price"])
            _last_spot_for_resolve["ts"] = now
            return _last_spot_for_resolve["price"]
    except Exception:
        pass
    return _last_spot_for_resolve.get("price")


@app.route("/api/gold-spot")
def api_gold_spot():
    """Multi-feed XAUUSD spot median for header + scalping (Stooq, Yahoo, ETF-implied)."""
    from screener.gold_war_room.fetch import fetch_spot_payload  # noqa: PLC0415

    force = request.args.get("force") == "1"
    try:
        spot = fetch_spot_payload(force=force)
        if spot.get("ok") and spot.get("price") is not None:
            _last_spot_for_resolve["price"] = float(spot["price"])
            _last_spot_for_resolve["ts"] = time.time()
            _schedule_async_resolve()
        return jsonify(spot)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e), "price": _last_spot_for_resolve.get("price")})


@app.route("/api/gold-war-room/performance")
def api_gold_war_room_performance():
    """Fast performance log — resolve runs in background only."""
    from screener.gold_war_room.performance import performance_summary  # noqa: PLC0415

    _schedule_async_resolve()
    try:
        perf = performance_summary()
    except Exception as e:
        traceback.print_exc()
        perf = {"total_signals_logged": 0, "recent_signals": [], "recent_scalps": [], "error": str(e)}
    return jsonify(_json_safe({"ok": True, "performance": perf}))


@app.route("/api/gold-war-room/stability")
def api_gold_war_room_stability():
    """Stability agent status (auto-heal tick)."""
    from screener.gold_war_room.stability import run_watchdog_tick  # noqa: PLC0415

    report = run_watchdog_tick(
        war_room_cache=_war_room_cache,
        war_room_lock=_war_room_lock,
        reset_compute_fn=_reset_war_room_compute_lock,
        load_seed_fn=_load_war_room_seed_into_cache,
        war_room_ready_fn=_war_room_ready,
    )
    return jsonify(_json_safe({"ok": True, "report": report}))


@app.route("/api/ping")
def api_ping():
    """Lightweight keep-alive for 24/7 uptime monitors (UptimeRobot, cron, etc.)."""
    return jsonify({
        "ok": True,
        "service": "gold-war-room",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    })


@app.route("/api/health")
def api_health():
    """Fast health check — must not block Render deploy (no heavy scan here)."""
    from dashboard.brand import SITE_NAME  # noqa: PLC0415
    from dashboard.launch import APP_VERSION  # noqa: PLC0415

    with _scan_lock:
        n = len((_scan_cache.get("data") or {}).get("all_stocks", []))
        scanning = _scan_cache["scanning"]
        err = _scan_cache["last_error"]
    live_n = 0
    if _live_engine is not None:
        try:
            live_n = _live_engine.get_payload().get("count", 0)
        except Exception:
            pass

    ourbit_n = 0
    congress_buys = 0
    try:
        from screener.ourbit_universe import get_ourbit_lookup  # noqa: PLC0415

        ourbit_n = len(get_ourbit_lookup())
    except Exception:
        pass

    try:
        from screener.congress_trades import get_congress_payload  # noqa: PLC0415

        cstats = (get_congress_payload(refresh=False).get("stats") or {})
        congress_buys = cstats.get("recent_buy_count", 0)
    except Exception:
        pass

    war_ok = False
    with _war_room_lock:
        war_ok = _war_room_ready(_war_room_cache.get("data"))
        war_computing = _war_room_cache.get("computing", False)

    return jsonify({
        "ok": True,
        "site": SITE_NAME,
        "version": APP_VERSION,
        "ourbit_listed": ourbit_n,
        "congress_buys": congress_buys,
        "stocks_cached": n,
        "live_quotes": live_n,
        "scanning": scanning,
        "error": err,
        "bg_started": _bg_started,
        "war_room_ready": war_ok,
        "war_room_computing": war_computing,
    })


@app.route("/api/ourbit-stocks")
def api_ourbit_stocks():
    """All tokenized stocks/ETFs listed on Ourbit (mapped to Yahoo tickers)."""
    from screener.ourbit_universe import get_ourbit_universe_meta  # noqa: PLC0415

    force = request.args.get("refresh") == "1"
    try:
        if force:
            from screener.ourbit_universe import fetch_ourbit_stocks, save_ourbit_cache  # noqa: PLC0415

            save_ourbit_cache(fetch_ourbit_stocks())
        meta = get_ourbit_universe_meta()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "stocks": [], "tickers": []})
    return jsonify({
        "ok": True,
        "count": meta.get("count", 0),
        "fetched_at": meta.get("fetched_at"),
        "source": meta.get("source"),
        "tickers": meta.get("tickers", []),
        "stocks": meta.get("stocks", []),
    })


@app.route("/api/congress-trades")
def api_congress_trades():
    """STOCK Act politician stock purchases — recent buys and edge-ranked tickers."""
    refresh = request.args.get("refresh") == "1"
    try:
        from screener.congress_trades import get_congress_payload  # noqa: PLC0415

        payload = get_congress_payload(refresh=refresh, lookback_days=180)
        return jsonify(_json_safe(payload))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e), "recent_buys": [], "edge_leaders": []})


@app.route("/api/bootstrap")
def api_bootstrap():
    """Fast first paint: return seed/disk cache immediately; live quotes patch in via /api/live."""
    _schedule_background_start()
    try:
        _load_disk_cache_into_memory()
        with _scan_lock:
            cached = _scan_cache.get("data")
            scanning = _scan_cache.get("scanning", False)
        if cached and cached.get("all_stocks"):
            data = dict(cached)
            data["ok"] = True
            data["scanning"] = scanning
            data["message"] = data.get("message") or "Data loaded — live quotes updating…"
            try:
                data = _enrich_hub_payload(data)
            except Exception:
                traceback.print_exc()
            return jsonify(_json_safe(_slim_hub_payload(data)))
        data = _bootstrap_from_live()
        data["ok"] = True
        data["scanning"] = scanning or not data.get("all_stocks")
        return jsonify(_json_safe(data))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": True, "error": str(e), "all_stocks": [], "scanning": True})


@app.route("/api/live")
def api_live():
    _schedule_background_start()
    return jsonify({"ok": True, **_live_payload_safe()})


@app.route("/api/market")
def api_market():
    """Live top gainers + losers for the header ticker."""
    _schedule_background_start()
    try:
        pulse = _build_movers_tape(start_bg=False)
        return jsonify({
            "ok": True,
            "pulse": pulse,
            "updated_at": time.strftime("%H:%M:%S"),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "pulse": [], "error": str(e)})


@app.route("/api/scan")
def api_scan():
    force = request.args.get("refresh") == "1"
    try:
        data = _scan_response(force=force)
        return jsonify(_json_safe(data))
    except Exception as e:
        traceback.print_exc()
        boot = _bootstrap_from_live()
        boot["error"] = str(e)
        return jsonify(_json_safe(boot))


@app.route("/api/alerts", methods=["GET"])
def api_alerts_get():
    store = load_alerts()
    with _alert_lock:
        feed = list(_alert_history)
    return jsonify({"ok": True, **store.to_dict(), "feed": feed})


@app.route("/api/alerts", methods=["POST"])
def api_alerts_post():
    body = request.get_json(silent=True) or {}
    symbol = (body.get("symbol") or "").upper().strip()
    alert_type = body.get("alert_type", "price_above")
    value = body.get("value")
    if not symbol or value is None:
        return jsonify({"ok": False, "error": "symbol and value required"}), 400
    valid = {
        "price_above", "price_below", "change_above", "change_below",
        "volume_above", "unusual_score_above",
    }
    if alert_type not in valid:
        return jsonify({"ok": False, "error": "invalid alert_type"}), 400
    alert = create_alert(symbol, alert_type, float(value), note=body.get("note", ""))
    return jsonify({"ok": True, "alert": alert.to_dict()})


@app.route("/api/alerts/<alert_id>", methods=["DELETE"])
def api_alerts_delete(alert_id: str):
    if delete_alert(alert_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/stream")
def api_stream():
    def generate():
        engine = _ensure_background()
        while True:
            payload = engine.get_payload()
            yield f"data: {json.dumps({'ok': True, **payload})}\n\n"
            time.sleep(float(_live_cfg().get("interval_sec", 1)))

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _schedule_background_start() -> None:
    """Start live engine + scan in background (never block HTTP responses)."""
    global _bg_scheduled
    if _bg_scheduled:
        return
    _bg_scheduled = True

    def _start() -> None:
        try:
            _ensure_background()
        except Exception as e:
            traceback.print_exc()
            with _scan_lock:
                _scan_cache["last_error"] = str(e)

    threading.Thread(target=_start, daemon=True, name="bg-start").start()


_war_room_warm_scheduled = False
_war_room_loop_started = False
_war_room_resolve_started = False


def _schedule_war_room_resolve_loop() -> None:
    """Background trade resolution — does not block user requests."""
    global _war_room_resolve_started
    if _war_room_resolve_started:
        return
    _war_room_resolve_started = True

    def _loop() -> None:
        while True:
            time.sleep(WAR_ROOM_RESOLVE_INTERVAL)
            _schedule_async_resolve()

    threading.Thread(target=_loop, daemon=True, name="war-room-resolve").start()


def _schedule_war_room_watchdog() -> None:
    """Stability agent: unstuck compute, reload seed, trim history."""
    global _war_room_watchdog_started
    if _war_room_watchdog_started:
        return
    _war_room_watchdog_started = True

    def _loop() -> None:
        from screener.gold_war_room.stability import run_watchdog_tick  # noqa: PLC0415

        while True:
            time.sleep(60 if is_cloud_host() else 45)
            try:
                report = run_watchdog_tick(
                    war_room_cache=_war_room_cache,
                    war_room_lock=_war_room_lock,
                    reset_compute_fn=_reset_war_room_compute_lock,
                    load_seed_fn=_load_war_room_seed_into_cache,
                    war_room_ready_fn=_war_room_ready,
                )
                if report.get("actions"):
                    print(f"War room stability: {', '.join(report['actions'])}")
                with _war_room_lock:
                    computing = _war_room_cache.get("computing", False)
                if (
                    not is_cloud_host()
                    and not computing
                    and not _war_room_ready(_war_room_cache.get("data"))
                ):
                    _refresh_war_room_async()
            except Exception as e:
                print(f"War room watchdog: {e}")

    threading.Thread(target=_loop, daemon=True, name="war-room-watchdog").start()


def _schedule_war_room_loop() -> None:
    """Re-run all agents on a fixed interval for live scalp / bias updates."""
    if is_cloud_host():
        return
    global _war_room_loop_started
    if _war_room_loop_started:
        return
    _war_room_loop_started = True

    def _loop() -> None:
        while True:
            time.sleep(WAR_ROOM_SCAN_INTERVAL)
            try:
                _refresh_war_room_async()
            except Exception as e:
                traceback.print_exc()
                print(f"War room loop error: {e}")

    threading.Thread(target=_loop, daemon=True, name="war-room-loop").start()


def _schedule_war_room_warmup() -> None:
    """Pre-compute Gold War Room so /api/gold-war-room responds quickly."""
    if is_cloud_host():
        return
    global _war_room_warm_scheduled
    if _war_room_warm_scheduled:
        return
    _war_room_warm_scheduled = True

    def _delayed() -> None:
        _refresh_war_room_async()

    threading.Thread(target=_delayed, daemon=True, name="war-room-warm").start()


def init_production() -> None:
    """Lightweight boot for gunicorn — Render health check must pass in seconds."""
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    _load_disk_cache_into_memory()
    with _scan_lock:
        has_stocks = bool((_scan_cache.get("data") or {}).get("all_stocks"))
    if is_cloud_host() and not has_stocks:
        seed = load_seed_bootstrap()
        if seed:
            try:
                seed = _enrich_hub_payload(seed)
            except Exception:
                traceback.print_exc()
            with _scan_lock:
                _scan_cache["data"] = seed
                _scan_cache["ts"] = time.time()
            print(f"Loaded {len(seed.get('all_stocks', []))} stocks from seed_bootstrap.json")
    _load_war_room_seed_into_cache()
    with _war_room_lock:
        _war_room_cache.setdefault("leverage", 100)
    _schedule_background_start()
    _schedule_war_room_loop()
    _schedule_war_room_resolve_loop()
    _schedule_war_room_watchdog()
    if not _war_room_ready(_war_room_cache.get("data")):
        _schedule_war_room_warmup()


def main(port: int | None = None) -> None:
    import os

    from dashboard.brand import SITE_NAME  # noqa: PLC0415
    from dashboard.launch import APP_VERSION, resolve_port  # noqa: PLC0415

    init_production()

    if os.environ.get("PORT"):
        print(f"{SITE_NAME} — use gunicorn in production (see GO_LIVE_FREE.md)")
        return

    listen_port = port if port is not None else resolve_port()
    if os.environ.get("STS_PORT"):
        listen_port = int(os.environ["STS_PORT"])
    host = os.environ.get("STS_HOST", "127.0.0.1")
    public_url = os.environ.get("STS_PUBLIC_URL", f"http://127.0.0.1:{listen_port}")
    try:
        (ROOT / "data" / "dashboard.url").write_text(public_url.rstrip("/") + "\n", encoding="utf-8")
    except OSError:
        pass
    print("=" * 50)
    print(SITE_NAME)
    print(f"Local:  http://127.0.0.1:{listen_port}")
    if public_url != f"http://127.0.0.1:{listen_port}":
        print(f"Public: {public_url}")
    print(f"Health: http://127.0.0.1:{listen_port}/api/health")
    if listen_port != 5050 and not os.environ.get("STS_PORT"):
        print(f"(Port 5050 was busy — using {listen_port} instead)")
    print("=" * 50)
    app.run(host=host, port=listen_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
