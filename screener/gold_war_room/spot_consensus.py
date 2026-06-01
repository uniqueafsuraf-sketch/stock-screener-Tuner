"""Multi-feed gold spot — median of several live sources (XAUUSD + COMEX cross-check)."""

from __future__ import annotations

import json
import statistics
import time
import urllib.request
from dataclasses import dataclass

_SPOT_CACHE: dict = {"payload": None, "ts": 0.0}
_SPOT_TTL = 12
_OUTLIER_PCT = 1.25  # drop quotes >1.25% from median


@dataclass
class _Quote:
    price: float
    change_pct: float
    source: str
    kind: str  # spot | comex | etf_implied
    symbol: str


def _http_get(url: str, timeout: int = 12) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StocksTunerStation/2.8"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _yahoo_chart(symbol: str) -> _Quote | None:
    enc = symbol.replace("=", "%3D")
    raw = _http_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?interval=1m&range=2d")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return None
        meta = result[0].get("meta") or {}
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        if price is None:
            return None
        price = float(price)
        prev = float(prev) if prev else price
        chg = ((price - prev) / prev) * 100 if prev else 0.0
        kind = "comex" if symbol in ("GC=F", "MGC=F") else "etf"
        return _Quote(round(price, 2), round(chg, 2), "yahoo_chart", kind, symbol)
    except Exception:
        return None


def _stooq_line(symbol: str, *, kind: str, label: str) -> _Quote | None:
    raw = _http_get(f"https://stooq.com/q/l/?s={symbol}")
    if not raw:
        return None
    try:
        line = raw.decode().strip().split("\n")[-1]
        if "N/D" in line:
            return None
        parts = line.split(",")
        if len(parts) < 7:
            return None
        # Stooq: symbol, date, time, open, high, low, close, [vol]
        close_raw = parts[6] if len(parts) > 6 and parts[6] else (parts[7] if len(parts) > 7 else "")
        if not close_raw:
            return None
        close = float(close_raw)
        open_ = float(parts[3]) if parts[3] else close
        chg = ((close - open_) / open_) * 100 if open_ else 0.0
        return _Quote(round(close, 2), round(chg, 2), "stooq", kind, label)
    except Exception:
        return None


def _median_filtered(quotes: list[_Quote]) -> float | None:
    if not quotes:
        return None
    prices = [q.price for q in quotes]
    med = statistics.median(prices)
    kept = [q for q in quotes if med and abs(q.price - med) / med * 100 <= _OUTLIER_PCT]
    if not kept:
        kept = quotes
    return round(statistics.median([q.price for q in kept]), 2)


def _collect_quotes() -> tuple[list[_Quote], list[_Quote]]:
    """Returns (spot_candidates, comex_candidates)."""
    spot: list[_Quote] = []
    comex: list[_Quote] = []

    xau_stooq = _stooq_line("xauusd", kind="spot", label="XAUUSD")
    if xau_stooq:
        spot.append(xau_stooq)

    gc_stooq = _stooq_line("gc.f", kind="comex", label="GC=F")
    if gc_stooq:
        comex.append(gc_stooq)

    for sym in ("GC=F", "MGC=F"):
        q = _yahoo_chart(sym)
        if q:
            q.kind = "comex"
            comex.append(q)

    gld_stooq = _stooq_line("gld.us", kind="etf", label="GLD")
    gld_yahoo = _yahoo_chart("GLD")
    iau_stooq = _stooq_line("iau.us", kind="etf", label="IAU")
    iau_yahoo = _yahoo_chart("IAU")

    spot_anchor = xau_stooq.price if xau_stooq else None
    if spot_anchor:
        seen_implied: set[str] = set()
        for anchor_etf, live_etf in (
            (iau_stooq, iau_yahoo),
            (gld_stooq, gld_yahoo),
        ):
            if not anchor_etf or not live_etf or not anchor_etf.price:
                continue
            key = f"{anchor_etf.symbol}:{live_etf.source}"
            if key in seen_implied:
                continue
            seen_implied.add(key)
            factor = spot_anchor / anchor_etf.price
            px = round(live_etf.price * factor, 2)
            spot.append(_Quote(
                px,
                live_etf.change_pct,
                f"{live_etf.source}_implied",
                "spot",
                f"{live_etf.symbol}→XAU",
            ))

    if not spot and comex:
        # Last resort: COMEX only (label clearly in UI)
        spot.extend(comex)

    return spot, comex


def fetch_consensus_spot(*, force: bool = False) -> dict:
    """
    Median XAUUSD spot from Stooq + Yahoo + ETF-implied; COMEX kept for reference.
    Matches TradingView OANDA:XAUUSD better than raw GC=F alone.
    """
    now = time.time()
    if (
        not force
        and _SPOT_CACHE["payload"] is not None
        and (now - _SPOT_CACHE["ts"]) < _SPOT_TTL
    ):
        return _SPOT_CACHE["payload"]

    spot_q, comex_q = _collect_quotes()
    spot_price = _median_filtered(spot_q)
    comex_price = _median_filtered(comex_q) if comex_q else None

    if spot_price is None and comex_price is not None:
        spot_price = comex_price

    chg_vals = [q.change_pct for q in spot_q if q.change_pct != 0]
    change_pct = round(statistics.mean(chg_vals), 2) if chg_vals else 0.0
    if spot_q and spot_q[0].change_pct:
        change_pct = spot_q[0].change_pct

    sources = []
    for q in spot_q + comex_q:
        sources.append({
            "source": q.source,
            "symbol": q.symbol,
            "kind": q.kind,
            "price": q.price,
            "change_pct": q.change_pct,
        })

    spread = None
    if spot_price and comex_price:
        spread = round(comex_price - spot_price, 2)

    payload = {
        "ok": spot_price is not None,
        "price": spot_price,
        "change_pct": change_pct,
        "symbol": "XAUUSD spot",
        "comex_price": comex_price,
        "spread_vs_comex": spread,
        "source": "consensus",
        "source_count": len(spot_q),
        "sources": sources,
        "display": f"XAUUSD spot ${spot_price:,.2f}" if spot_price else None,
        "scalp_label": f"XAUUSD spot ${spot_price:,.2f}" if spot_price else None,
    }
    _SPOT_CACHE["payload"] = payload
    _SPOT_CACHE["ts"] = now
    return payload


def consensus_tuple() -> tuple[float, float, str] | None:
    """Backward-compatible (price, change_pct, symbol) for fetch.py."""
    p = fetch_consensus_spot()
    if not p.get("ok") or p.get("price") is None:
        return None
    return p["price"], p.get("change_pct") or 0.0, "XAUUSD spot"
