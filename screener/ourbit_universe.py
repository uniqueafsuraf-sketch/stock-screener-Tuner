"""Fetch every tokenized US stock / ETF listed on Ourbit (futures API)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

OURBIT_EXCHANGE_INFO = "https://api.ourbit.com/api/v3/exchangeInfo"
OURBIT_FUTURES_DETAIL = "https://futures.ourbit.com/api/v1/contract/detail"
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "ourbit_stocks.json"
STATIC_CACHE_PATH = (
    Path(__file__).resolve().parent.parent / "dashboard" / "static" / "ourbit_stocks.json"
)
CACHE_TTL_SEC = 3600
_STOCK_FUTURES_PLATE = "ob_trade_zone_stock"

# Base assets that end in ON but are not Ourbit tokenized equities
_EXCLUDE_BASE = frozenset({
    "ON", "TON", "MON", "RON", "RION", "AEON", "ANON", "AUCTION", "ECHELON",
})

_TICKER_OVERRIDES = {
    "GOOGLON": "GOOGL",
}

# Ourbit futures baseCoin → Yahoo / screener symbol
_YAHOO_TICKER_OVERRIDES = {
    "BRKB": "BRK-B",
}


def ourbit_base_to_ticker(base_asset: str) -> str:
    ba = (base_asset or "").upper().strip()
    if ba in _TICKER_OVERRIDES:
        return _TICKER_OVERRIDES[ba]
    if ba.endswith("ON") and len(ba) > 2:
        return ba[:-2]
    return ba


def ourbit_futures_to_ticker(base_coin: str) -> str:
    bc = (base_coin or "").upper().strip()
    return _YAHOO_TICKER_OVERRIDES.get(bc, bc)


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


def _fetch_spot_tokenized_stocks(*, timeout: int = 45) -> list[dict]:
    """Live pull from Ourbit spot API — enabled tokenized stock/ETF USDT pairs (*ON)."""
    req = urllib.request.Request(
        OURBIT_EXCHANGE_INFO,
        headers={"User-Agent": "StocksTunerStation/4.2 (+ourbit-spot)"},
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
            "market": "spot",
        })
    return rows


def _fetch_futures_stock_contracts(*, timeout: int = 45) -> list[dict]:
    """Ourbit US stock perpetuals (NOK_USDT, AAPL_USDT, …) from futures API."""
    req = urllib.request.Request(
        OURBIT_FUTURES_DETAIL,
        headers={"User-Agent": "StocksTunerStation/4.2 (+ourbit-futures)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())

    rows: list[dict] = []
    for row in payload.get("data") or []:
        if _STOCK_FUTURES_PLATE not in (row.get("conceptPlate") or []):
            continue
        if row.get("state") not in (0, "0", None):
            continue
        base = (row.get("baseCoin") or "").upper().strip()
        sym = row.get("symbol") or ""
        if not base or not sym.endswith("_USDT"):
            continue
        rows.append({
            "ourbit_base": base,
            "ourbit_symbol": sym,
            "ticker": ourbit_futures_to_ticker(base),
            "spot_allowed": False,
            "market": "futures",
            "is_new": bool(row.get("isNew")),
        })
    return rows


def _merge_ourbit_rows(spot_rows: list[dict], futures_rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in spot_rows:
        t = row["ticker"].upper()
        merged[t] = dict(row)
    for row in futures_rows:
        t = row["ticker"].upper()
        if t in merged:
            cur = merged[t]
            cur["ourbit_futures_symbol"] = row["ourbit_symbol"]
            cur["markets"] = sorted({cur.get("market", "spot"), "futures"})
            if row.get("is_new"):
                cur["is_new"] = True
        else:
            merged[t] = dict(row)
    out = list(merged.values())
    out.sort(key=lambda r: r["ticker"])
    return out


def fetch_ourbit_stocks(*, timeout: int = 45) -> list[dict]:
    """All Ourbit-listed US stocks/ETFs: spot *ON pairs + futures stock zone."""
    spot_rows: list[dict] = []
    futures_rows: list[dict] = []
    try:
        spot_rows = _fetch_spot_tokenized_stocks(timeout=timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    try:
        futures_rows = _fetch_futures_stock_contracts(timeout=timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    if not spot_rows and not futures_rows:
        raise RuntimeError("Ourbit fetch failed: no spot or futures stock data")
    return _merge_ourbit_rows(spot_rows, futures_rows)


def save_ourbit_cache(rows: list[dict]) -> Path:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "source": "api.ourbit.com + futures.ourbit.com (spot *ON + stock futures)",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "fetched_at_epoch": time.time(),
        "count": len(rows),
        "stocks": rows,
        "tickers": [r["ticker"] for r in rows],
    }
    CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return CACHE_PATH


def _read_ourbit_cache_file(path: Path, *, max_age_sec: int) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched = data.get("fetched_at_epoch") or 0
        if fetched and time.time() - fetched > max_age_sec:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def load_ourbit_cache(*, max_age_sec: int = CACHE_TTL_SEC) -> dict | None:
    data = _read_ourbit_cache_file(CACHE_PATH, max_age_sec=max_age_sec)
    if data and data.get("stocks"):
        return data
    return _read_ourbit_cache_file(STATIC_CACHE_PATH, max_age_sec=86400 * 365)


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


def get_ourbit_lookup(*, refresh: bool = False, allow_fetch: bool = True) -> dict[str, dict]:
    """Map Yahoo ticker → Ourbit pair metadata."""
    if refresh and allow_fetch:
        rows = fetch_ourbit_stocks()
        save_ourbit_cache(rows)
        return {r["ticker"].upper(): r for r in rows}

    cached = load_ourbit_cache(max_age_sec=86400 * 7)
    if cached and cached.get("stocks"):
        rows = cached["stocks"]
    elif allow_fetch:
        try:
            rows = fetch_ourbit_stocks()
            save_ourbit_cache(rows)
        except Exception:
            rows = []
    else:
        rows = []

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
