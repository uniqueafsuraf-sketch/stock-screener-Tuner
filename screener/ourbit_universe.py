"""Fetch every tokenized US stock / ETF listed on Ourbit (futures API)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

OURBIT_EXCHANGE_INFO = "https://api.ourbit.com/api/v3/exchangeInfo"
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "ourbit_stocks.json"
CACHE_TTL_SEC = 3600

# Base assets that end in ON but are not Ourbit tokenized equities
_EXCLUDE_BASE = frozenset({
    "ON", "TON", "MON", "RON", "RION", "AEON", "ANON", "AUCTION", "ECHELON",
})

_TICKER_OVERRIDES = {
    "GOOGLON": "GOOGL",
}


def ourbit_base_to_ticker(base_asset: str) -> str:
    ba = (base_asset or "").upper().strip()
    if ba in _TICKER_OVERRIDES:
        return _TICKER_OVERRIDES[ba]
    if ba.endswith("ON") and len(ba) > 2:
        return ba[:-2]
    return ba


def _is_ourbit_tokenized_stock(symbol_row: dict) -> bool:
    if symbol_row.get("status") != "ENABLED":
        return False
    if symbol_row.get("quoteAsset") != "USDT":
        return False
    base = symbol_row.get("baseAsset") or ""
    sym = symbol_row.get("symbol") or ""
    if sym != f"{base}USDT":
        return False
    if not base.endswith("ON") or len(base) < 4:
        return False
    if base in _EXCLUDE_BASE:
        return False
    return True


def fetch_ourbit_stocks(*, timeout: int = 45) -> list[dict]:
    """Live pull from Ourbit — all enabled tokenized stock/ETF USDT pairs."""
    req = urllib.request.Request(
        OURBIT_EXCHANGE_INFO,
        headers={"User-Agent": "StocksTunerStation/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())

    rows: list[dict] = []
    for row in payload.get("symbols") or []:
        if not _is_ourbit_tokenized_stock(row):
            continue
        base = row["baseAsset"]
        rows.append({
            "ourbit_base": base,
            "ourbit_symbol": row["symbol"],
            "ticker": ourbit_base_to_ticker(base),
            "spot_allowed": bool(row.get("isSpotTradingAllowed")),
        })

    rows.sort(key=lambda r: r["ticker"])
    # Deduplicate by ticker (keep first Ourbit pair)
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        out.append(r)
    return out


def save_ourbit_cache(rows: list[dict]) -> Path:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "source": "api.ourbit.com/api/v3/exchangeInfo",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "fetched_at_epoch": time.time(),
        "count": len(rows),
        "stocks": rows,
        "tickers": [r["ticker"] for r in rows],
    }
    CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return CACHE_PATH


def load_ourbit_cache(*, max_age_sec: int = CACHE_TTL_SEC) -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        fetched = data.get("fetched_at_epoch") or 0
        if not fetched:
            return data
        if time.time() - fetched > max_age_sec:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def get_ourbit_tickers(*, refresh: bool = False) -> list[str]:
    """Tickers for Yahoo/screener (AAPL, TSLA, …) mapped from Ourbit *ON assets."""
    if not refresh:
        cached = load_ourbit_cache()
        if cached and cached.get("tickers"):
            return list(cached["tickers"])

    try:
        rows = fetch_ourbit_stocks()
        save_ourbit_cache(rows)
        return [r["ticker"] for r in rows]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        if CACHE_PATH.exists():
            try:
                fallback = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                tickers = fallback.get("tickers") or []
                if tickers:
                    return list(tickers)
            except (json.JSONDecodeError, OSError):
                pass
        raise RuntimeError(f"Ourbit symbol fetch failed: {e}") from e


def get_ourbit_lookup(*, refresh: bool = False) -> dict[str, dict]:
    """Map Yahoo ticker → Ourbit pair metadata."""
    if refresh:
        rows = fetch_ourbit_stocks()
        save_ourbit_cache(rows)
    else:
        cached = load_ourbit_cache()
        if cached and cached.get("stocks"):
            rows = cached["stocks"]
        else:
            rows = fetch_ourbit_stocks()
            save_ourbit_cache(rows)
    return {r["ticker"].upper(): r for r in rows}


def sync_ourbit_stocks(*, refresh: bool = True) -> dict:
    """Refresh Ourbit stock list; return newly discovered tickers."""
    old_tickers: set[str] = set()
    if CACHE_PATH.exists():
        try:
            prev = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            old_tickers = {t.upper() for t in (prev.get("tickers") or [])}
        except (json.JSONDecodeError, OSError):
            pass

    rows = fetch_ourbit_stocks() if refresh else []
    if not rows:
        cached = load_ourbit_cache(max_age_sec=86400 * 7)
        rows = (cached or {}).get("stocks") or []
    save_ourbit_cache(rows)

    current = {r["ticker"].upper() for r in rows}
    new_tickers = sorted(current - old_tickers)
    return {
        "new_tickers": new_tickers,
        "total": len(rows),
        "tickers": sorted(current),
    }


def get_ourbit_universe_meta() -> dict:
    """Full metadata for dashboard / API."""
    try:
        rows = fetch_ourbit_stocks()
        save_ourbit_cache(rows)
    except Exception:
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            return data
        raise
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
