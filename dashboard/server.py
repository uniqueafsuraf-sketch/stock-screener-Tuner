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
            "universe": cfg.get("universe", "both"),
            "live": live,
            "news": news,
        }
    return cfg


def _live_cfg() -> dict:
    return _cfg().get("live", {})


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


def _stock_from_quote(sym: str, q: dict) -> dict:
    chg = float(q.get("change_pct") or 0)
    vol = float(q.get("volume_ratio") or 0)
    return {
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
    }


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
        with _scan_lock:
            if _scan_cache["data"] is None:
                _scan_cache["data"] = disk
                _scan_cache["ts"] = time.time()
                print(f"Loaded {len(disk.get('all_stocks', []))} stocks from {src}")


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
    return data


def _run_scan(force: bool = False) -> None:
    with _scan_lock:
        if _scan_cache["scanning"] and not force:
            return
        _scan_cache["scanning"] = True
        _scan_cache["last_error"] = None

    print("Starting full market scan…")
    try:
        cfg = _cfg()
        result = scan_full(config=cfg, use_batch=True)
        payload = {
            **result.to_dict(),
            "ok": True,
            "scanning": False,
            "universe_size": len(resolve_symbols(cfg)),
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
    _ensure_background()

    if force:
        with _scan_lock:
            already = _scan_cache["scanning"]
        if not already:
            threading.Thread(target=lambda: _run_scan(force=True), daemon=True).start()

    with _scan_lock:
        cached = _scan_cache["data"]
        scanning = _scan_cache["scanning"]

    if cached and cached.get("all_stocks"):
        merged = _merge_scan_with_live(cached)
        merged["ok"] = True
        merged["scanning"] = scanning
        return merged

    # No full scan yet — return live bootstrap immediately
    boot = _bootstrap_from_live()
    boot["scanning"] = scanning or not boot.get("all_stocks")
    return _merge_scan_with_live(boot)


@app.route("/")
def index():
    _schedule_background_start()
    return render_template("index.html")


@app.route("/gold-war-room")
def gold_war_room_page():
    from dashboard.brand import SITE_NAME  # noqa: PLC0415

    _schedule_background_start()
    _schedule_war_room_warmup()
    return render_template("gold_war_room.html", site_name=SITE_NAME)


_war_room_cache: dict = {"data": None, "ts": 0.0, "computing": False, "computing_since": 0.0}
_war_room_lock = threading.Lock()
WAR_ROOM_TTL = 90
WAR_ROOM_COMPUTE_MAX = 75


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
        "symbol": "XAUUSD (GC)",
        "market_bias": {"bias": "—", "confidence": 0, "why": "Analysis in progress…"},
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

        try:
            payload = run_war_room_analysis()
            if payload.get("ok"):
                save_war_room_seed(payload)
            with _war_room_lock:
                _war_room_cache["data"] = payload
                _war_room_cache["ts"] = time.time()
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

    threading.Thread(target=_run, daemon=True, name="war-room-refresh").start()


@app.route("/api/gold-war-room")
def api_gold_war_room():
    force = request.args.get("refresh") == "1"
    now = time.time()
    with _war_room_lock:
        cached = _war_room_cache.get("data")
        age = now - (_war_room_cache.get("ts") or 0)
        computing = _war_room_cache.get("computing", False)
        started = _war_room_cache.get("computing_since") or 0.0

    if computing and started and (now - started) > WAR_ROOM_COMPUTE_MAX:
        _reset_war_room_compute_lock()
        computing = False

    if _war_room_ready(cached) and age < WAR_ROOM_TTL and not force:
        return jsonify(_json_safe(cached))

    if _war_room_ready(cached) and not force:
        return jsonify(_json_safe(cached))

    if not computing:
        _refresh_war_room_async(force=force)

    if _war_room_ready(cached):
        out = dict(cached)
        if force or age >= WAR_ROOM_TTL:
            out["stale"] = True
        return jsonify(_json_safe(out))

    return jsonify(_json_safe(_war_room_warming_payload()))


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

    return jsonify({
        "ok": True,
        "site": SITE_NAME,
        "version": APP_VERSION,
        "stocks_cached": n,
        "live_quotes": live_n,
        "scanning": scanning,
        "error": err,
        "bg_started": _bg_started,
    })


@app.route("/api/bootstrap")
def api_bootstrap():
    """Fast first paint: return seed/disk cache immediately; live quotes patch in via /api/live."""
    _schedule_background_start()
    try:
        with _scan_lock:
            cached = _scan_cache.get("data")
            scanning = _scan_cache.get("scanning", False)
        if cached and cached.get("all_stocks"):
            data = dict(cached)
            data["ok"] = True
            data["scanning"] = scanning
            data["message"] = data.get("message") or "Data loaded — live quotes updating…"
            return jsonify(_json_safe(_merge_scan_with_live(data, start_bg=False)))
        data = _bootstrap_from_live()
        return jsonify(_json_safe(_merge_scan_with_live(data, start_bg=False)))
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


def _schedule_war_room_warmup() -> None:
    """Pre-compute Gold War Room so /api/gold-war-room responds quickly."""
    global _war_room_warm_scheduled
    if _war_room_warm_scheduled:
        return
    _war_room_warm_scheduled = True

    def _delayed() -> None:
        if is_cloud_host():
            time.sleep(30)
        _refresh_war_room_async()

    threading.Thread(target=_delayed, daemon=True, name="war-room-warm").start()


def init_production() -> None:
    """Lightweight boot for gunicorn — Render health check must pass in seconds."""
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    _load_disk_cache_into_memory()
    if is_cloud_host() and _scan_cache.get("data") is None:
        seed = load_seed_bootstrap()
        if seed:
            with _scan_lock:
                _scan_cache["data"] = seed
                _scan_cache["ts"] = time.time()
            print(f"Loaded {len(seed.get('all_stocks', []))} stocks from seed_bootstrap.json")
    _load_war_room_seed_into_cache()
    _schedule_background_start()
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
