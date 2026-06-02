"""Congressional stock disclosures (STOCK Act) — Senate + House, edge scoring."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "congress_trades.json"
STATIC_PATH = (
    Path(__file__).resolve().parent.parent / "dashboard" / "static" / "congress_trades.json"
)
CACHE_TTL_SEC = 3600

CONGRESSINVESTS_URL = "https://congressinfor-production.up.railway.app/trades"
SENATE_ARCHIVE_URL = (
    "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/"
    "master/aggregate/all_transactions.json"
)

AMOUNT_TIERS = (
    "$1,001 - $15,000",
    "$15,001 - $50,000",
    "$50,001 - $100,000",
    "$100,001 - $250,000",
    "$250,001 - $500,000",
    "$500,001 - $1,000,000",
    "$1,000,001 - $5,000,000",
    "$5,000,001 - $25,000,000",
    "$25,000,001 - $50,000,000",
    "$50,000,001 +",
)

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _fetch_json(url: str, *, timeout: int = 90) -> list | dict | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "StocksTunerStation/4.0 (+congress-trades)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _parse_date(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt)
        except ValueError:
            continue
    return None


def _norm_ticker(raw: str | None) -> str:
    t = (raw or "").upper().strip()
    if not t or t in ("--", "N/A", "NA"):
        return ""
    if not _TICKER_RE.match(t):
        return ""
    return t


def _is_purchase(tx_type: str | None) -> bool:
    t = (tx_type or "").lower()
    return "purchase" in t or t.startswith("buy")


def _is_sale(tx_type: str | None) -> bool:
    t = (tx_type or "").lower()
    return "sale" in t or "sell" in t


def _amount_score(amount: str | None) -> int:
    cleaned = _clean_amount(amount)
    if not cleaned or cleaned == "—":
        return 1
    try:
        idx = AMOUNT_TIERS.index(cleaned)
    except ValueError:
        for i, tier in enumerate(AMOUNT_TIERS):
            if tier.split()[0] in cleaned and tier.split()[-1] in cleaned:
                return min(10, 1 + i)
        return 1
    return min(10, 1 + idx)


def _clean_amount(raw: str | None) -> str:
    if not raw:
        return "—"
    s = re.sub(r"\s+", " ", str(raw).replace("\n", " ")).strip()
    for tier in AMOUNT_TIERS:
        if tier in s:
            return tier
    m = re.search(r"\$[\d,]+ - \$[\d,]+", s)
    if m:
        return m.group(0)
    return s[:48] or "—"


def _norm_cinvests(row: dict) -> dict | None:
    ticker = _norm_ticker(row.get("ticker"))
    if not ticker:
        return None
    politician = (row.get("member") or "").strip()
    if not politician:
        return None
    tx_date = _parse_date(row.get("tx_date"))
    disc_date = _parse_date(row.get("disclosed"))
    when = tx_date or disc_date
    if not when:
        return None
    if when > datetime.now() + timedelta(days=3):
        return None
    trade_type = (row.get("trade_type") or "").strip()
    amount = _clean_amount(row.get("amount"))
    return {
        "symbol": ticker,
        "politician": politician,
        "chamber": row.get("chamber") or "Congress",
        "owner": "—",
        "type": trade_type,
        "side": "buy" if trade_type == "buy" else "sell" if trade_type == "sell" else "other",
        "amount": amount,
        "amount_score": _amount_score(amount),
        "transaction_date": row.get("tx_date") or "",
        "disclosure_date": row.get("disclosed") or "",
        "when": when.strftime("%Y-%m-%d"),
        "days_ago": max(0, (datetime.now() - when).days),
        "ptr_link": row.get("link") or "",
        "asset_description": (row.get("asset") or "")[:120],
    }


def _fetch_congressinvests(*, lookback_days: int = 180) -> list[dict]:
    """Live Senate + House PTR feed (CongressInvests public API)."""
    cutoff = datetime.now() - timedelta(days=lookback_days)
    out: list[dict] = []
    offset = 0
    limit = 200
    max_batches = 8

    for _ in range(max_batches):
        url = f"{CONGRESSINVESTS_URL}?limit={limit}&offset={offset}"
        data = _fetch_json(url, timeout=45)
        if not isinstance(data, dict):
            break
        batch = data.get("trades") or []
        if not batch:
            break
        stop_early = False
        for row in batch:
            if not isinstance(row, dict):
                continue
            tx = _norm_cinvests(row)
            if not tx:
                continue
            when = _parse_date(tx["when"])
            if when and when >= cutoff:
                out.append(tx)
            elif when and when < cutoff:
                stop_early = True
                break
        if stop_early or not data.get("has_more"):
            break
        offset += limit
    return out


def _norm_tx(row: dict, *, chamber: str) -> dict | None:
    ticker = _norm_ticker(row.get("ticker"))
    if not ticker:
        desc = row.get("asset_description") or ""
        m = re.search(r"\b([A-Z]{1,5})\s+-", desc)
        if m:
            ticker = _norm_ticker(m.group(1))
    if not ticker:
        return None

    asset_type = (row.get("asset_type") or "").lower()
    if asset_type and "stock" not in asset_type and "option" not in asset_type:
        if "bond" in asset_type or "note" in asset_type:
            return None

    politician = (
        row.get("senator")
        or row.get("representative")
        or row.get("politician")
        or ""
    ).strip()
    if not politician:
        return None

    tx_date = _parse_date(row.get("transaction_date"))
    disc_date = _parse_date(row.get("disclosure_date"))
    when = tx_date or disc_date
    if not when:
        return None

    tx_type = row.get("type") or ""
    return {
        "symbol": ticker,
        "politician": politician,
        "chamber": chamber,
        "owner": row.get("owner") or "—",
        "type": tx_type,
        "side": "buy" if _is_purchase(tx_type) else "sell" if _is_sale(tx_type) else "other",
        "amount": row.get("amount") or "—",
        "amount_score": _amount_score(row.get("amount")),
        "transaction_date": row.get("transaction_date") or "",
        "disclosure_date": row.get("disclosure_date") or "",
        "when": when.strftime("%Y-%m-%d"),
        "days_ago": (datetime.now() - when).days,
        "ptr_link": row.get("ptr_link") or row.get("ptr_url") or "",
        "asset_description": (row.get("asset_description") or "")[:120],
    }


def fetch_congress_trades(*, lookback_days: int = 180) -> list[dict]:
    """Pull Senate + House STOCK Act filings from public sources."""
    live = _fetch_congressinvests(lookback_days=lookback_days)
    if live:
        return live

    out: list[dict] = []
    senate = _fetch_json(SENATE_ARCHIVE_URL)
    if isinstance(senate, list):
        cutoff = datetime.now() - timedelta(days=lookback_days)
        for row in senate:
            if not isinstance(row, dict):
                continue
            tx = _norm_tx(row, chamber="Senate")
            if tx and _parse_date(tx.get("when")) and _parse_date(tx["when"]) >= cutoff:
                out.append(tx)
    return out


def _score_ticker(trades: list[dict], *, lookback_days: int = 90) -> dict:
    cutoff = datetime.now() - timedelta(days=lookback_days)
    buys: list[dict] = []
    sells: list[dict] = []
    politicians: set[str] = set()
    chambers: set[str] = set()
    score = 0.0

    for t in trades:
        when = _parse_date(t.get("when"))
        if not when or when < cutoff:
            continue
        politicians.add(t["politician"])
        chambers.add(t["chamber"])
        recency = max(0.3, 1.0 - (t.get("days_ago", 90) / max(lookback_days, 1)))
        if t["side"] == "buy":
            buys.append(t)
            score += t["amount_score"] * 2.5 * recency
        elif t["side"] == "sell":
            sells.append(t)
            score -= t["amount_score"] * 0.8 * recency

    if len(politicians) >= 2:
        score += 6
    if len(politicians) >= 3:
        score += 8
    if chambers == {"Senate", "House"}:
        score += 10

    score = round(min(100, max(0, score)), 1)
    last_buy = max((b["when"] for b in buys), default="")
    return {
        "congress_edge": score,
        "congress_buys": len(buys),
        "congress_sells": len(sells),
        "congress_politicians": sorted(politicians),
        "congress_chambers": sorted(chambers),
        "congress_last_buy": last_buy,
        "congress_trades": sorted(buys + sells, key=lambda x: x["when"], reverse=True)[:12],
    }


def build_congress_payload(*, lookback_days: int = 180) -> dict:
    trades = fetch_congress_trades(lookback_days=lookback_days)
    by_symbol: dict[str, list[dict]] = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    ticker_edges: dict[str, dict] = {}
    for sym, sym_trades in by_symbol.items():
        ticker_edges[sym] = _score_ticker(sym_trades, lookback_days=90)

    recent = sorted(trades, key=lambda x: x["when"], reverse=True)
    buy_recent = [t for t in recent if t["side"] == "buy"][:80]
    edge_leaders = sorted(
        (
            {
                "symbol": sym,
                **meta,
            }
            for sym, meta in ticker_edges.items()
            if meta["congress_buys"] > 0
        ),
        key=lambda x: (-x["congress_edge"], -x["congress_buys"]),
    )[:40]

    return {
        "ok": True,
        "source": "CongressInvests API · official Senate EFD + House Clerk PTR filings",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "fetched_at_epoch": time.time(),
        "lookback_days": lookback_days,
        "total_trades": len(trades),
        "recent_buys": buy_recent,
        "edge_leaders": edge_leaders,
        "by_symbol": ticker_edges,
        "stats": {
            "symbols_with_buys": sum(1 for m in ticker_edges.values() if m["congress_buys"] > 0),
            "recent_buy_count": len(buy_recent),
            "senate_trades": sum(1 for t in trades if t["chamber"] == "Senate"),
            "house_trades": sum(1 for t in trades if t["chamber"] == "House"),
        },
    }


def save_congress_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":"))
    CACHE_PATH.write_text(raw, encoding="utf-8")
    STATIC_PATH.write_text(raw, encoding="utf-8")


def load_congress_cache(*, max_age_sec: int = CACHE_TTL_SEC) -> dict | None:
    for path in (CACHE_PATH, STATIC_PATH):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - (data.get("fetched_at_epoch") or 0)
            if data.get("by_symbol") and age <= max_age_sec:
                return data
            if data.get("by_symbol"):
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def get_congress_payload(*, refresh: bool = False, lookback_days: int = 180) -> dict:
    if not refresh:
        cached = load_congress_cache(max_age_sec=86400 * 7)
        if cached:
            return cached
    try:
        payload = build_congress_payload(lookback_days=lookback_days)
        save_congress_cache(payload)
        return payload
    except Exception as e:
        cached = load_congress_cache(max_age_sec=86400 * 365)
        if cached:
            cached["stale"] = True
            cached["error"] = str(e)
            return cached
        return {
            "ok": False,
            "error": str(e),
            "recent_buys": [],
            "edge_leaders": [],
            "by_symbol": {},
            "stats": {},
        }


def get_congress_lookup(*, refresh: bool = False) -> dict[str, dict]:
    return get_congress_payload(refresh=refresh).get("by_symbol") or {}


def tag_row_with_congress(row: dict, lookup: dict[str, dict]) -> dict:
    sym = (row.get("symbol") or "").upper()
    meta = lookup.get(sym)
    if not meta or not meta.get("congress_buys"):
        return row
    out = dict(row)
    out["congress_edge"] = meta.get("congress_edge", 0)
    out["congress_buys"] = meta.get("congress_buys", 0)
    out["congress_politicians"] = meta.get("congress_politicians", [])
    out["congress_last_buy"] = meta.get("congress_last_buy", "")
    out["congress_trades"] = meta.get("congress_trades", [])[:4]
    signals = list(out.get("signals") or [])
    if "CONGRESS_BUY" not in signals and meta.get("congress_buys", 0) > 0:
        signals.append("CONGRESS_BUY")
    out["signals"] = signals
    pols = ", ".join(meta.get("congress_politicians", [])[:2])
    note = f"Congress buy: {meta['congress_buys']} purchase(s) · {pols}"
    notes = list(out.get("notes") or [])
    if note not in notes:
        notes.insert(0, note)
    out["notes"] = notes[:6]
    base_edge = float(out.get("edge_score") or 0)
    boost = min(24, meta.get("congress_edge", 0) * 0.38)
    out["edge_score"] = round(min(100, base_edge + boost), 1)
    if meta.get("congress_edge", 0) >= 25 and not out.get("has_opportunity"):
        out["has_opportunity"] = True
    return out
