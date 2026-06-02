"""Congressional stock disclosures (STOCK Act) — multi-source, min-size buys."""

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
CACHE_TTL_SEC = 1800
MIN_BUY_USD_DEFAULT = 5000

CONGRESSINVESTS_URL = "https://congressinfor-production.up.railway.app/trades"
CAPITOL_EXPOSED_URL = "https://www.capitolexposed.com/api/v1/trades"

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


def _congress_cfg() -> dict:
    try:
        from screener.scan import load_config  # noqa: PLC0415

        return load_config().get("congress") or {}
    except Exception:
        return {}


def min_buy_usd() -> int:
    return int(_congress_cfg().get("min_buy_usd", MIN_BUY_USD_DEFAULT))


def lookback_days_default() -> int:
    return int(_congress_cfg().get("lookback_days", 180))


def _fetch_json(url: str, *, timeout: int = 90) -> list | dict | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "StocksTunerStation/4.3 (+congress-trades)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _parse_date(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt)
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
    if "$50,000,001" in s or "$50,000,001 +" in s:
        return "$50,000,001 +"
    return s[:48] or "—"


def _amount_bounds(amount: str | None) -> tuple[int, int | None]:
    cleaned = _clean_amount(amount)
    if cleaned == "$50,000,001 +":
        return 50_000_001, None
    nums = [int(x.replace(",", "")) for x in re.findall(r"\$?([\d,]+)", cleaned) if x]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]
    return 0, None


def _amount_score(amount: str | None) -> int:
    lo, _ = _amount_bounds(amount)
    if lo >= 1_000_001:
        return 10
    if lo >= 250_001:
        return 8
    if lo >= 100_001:
        return 7
    if lo >= 50_001:
        return 6
    if lo >= 15_001:
        return 4
    if lo >= 5_000:
        return 2
    return 1


def _meets_min_buy(*, amount: str | None = None, amount_min: int | None = None) -> bool:
    floor = min_buy_usd()
    if amount_min is not None:
        return int(amount_min) >= floor
    lo, _ = _amount_bounds(amount)
    return lo >= floor


def _norm_cinvests(row: dict) -> dict | None:
    if (row.get("trade_type") or "").strip().lower() != "buy":
        return None
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
    amount = _clean_amount(row.get("amount"))
    lo, hi = _amount_bounds(amount)
    if not _meets_min_buy(amount=amount, amount_min=lo):
        return None
    return {
        "symbol": ticker,
        "politician": politician,
        "chamber": row.get("chamber") or "Congress",
        "owner": "—",
        "type": "buy",
        "side": "buy",
        "amount": amount,
        "amount_min_usd": lo,
        "amount_max_usd": hi,
        "amount_score": _amount_score(amount),
        "transaction_date": row.get("tx_date") or "",
        "disclosure_date": row.get("disclosed") or "",
        "when": when.strftime("%Y-%m-%d"),
        "days_ago": max(0, (datetime.now() - when).days),
        "ptr_link": row.get("link") or "",
        "asset_description": (row.get("asset") or "")[:120],
        "sources": ["congressinvests"],
    }


def _norm_capitolexposed(row: dict) -> dict | None:
    if (row.get("transaction_type") or "").lower() != "purchase":
        return None
    ticker = _norm_ticker(row.get("ticker"))
    if not ticker:
        return None
    politician = (row.get("member_name") or "").strip()
    if not politician:
        return None
    try:
        lo = int(row.get("amount_min") or 0)
        hi = int(row.get("amount_max") or 0) if row.get("amount_max") else None
    except (TypeError, ValueError):
        lo, hi = 0, None
    if not _meets_min_buy(amount_min=lo):
        return None
    tx_date = _parse_date(row.get("transaction_date"))
    disc_date = _parse_date(row.get("disclosure_date"))
    when = tx_date or disc_date
    if not when:
        return None
    if when > datetime.now() + timedelta(days=3):
        return None
    amount = f"${lo:,}" + (f" - ${hi:,}" if hi else "")
    trade_id = row.get("id") or ""
    chamber = "Senate" if "senate" in trade_id else "House"
    return {
        "symbol": ticker,
        "politician": politician,
        "chamber": chamber,
        "owner": row.get("owner") or "—",
        "type": "purchase",
        "side": "buy",
        "amount": amount,
        "amount_min_usd": lo,
        "amount_max_usd": hi,
        "amount_score": _amount_score(amount),
        "transaction_date": (tx_date.strftime("%Y-%m-%d") if tx_date else ""),
        "disclosure_date": (disc_date.strftime("%Y-%m-%d") if disc_date else ""),
        "when": when.strftime("%Y-%m-%d"),
        "days_ago": max(0, (datetime.now() - when).days),
        "ptr_link": row.get("source_url") or "",
        "asset_description": (row.get("asset_description") or "")[:120],
        "sources": ["capitolexposed"],
    }


def _fetch_congressinvests(*, lookback_days: int = 180) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=lookback_days)
    out: list[dict] = []
    offset = 0
    limit = 200
    max_batches = 12

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


def _fetch_capitolexposed(*, lookback_days: int = 180) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=lookback_days)
    out: list[dict] = []
    page = 1
    per_page = 50
    max_pages = 8

    while page <= max_pages:
        url = f"{CAPITOL_EXPOSED_URL}?per_page={per_page}&page={page}"
        data = _fetch_json(url, timeout=45)
        if not isinstance(data, dict):
            break
        batch = data.get("data") or []
        if not batch:
            break
        stop_early = False
        for row in batch:
            if not isinstance(row, dict):
                continue
            tx = _norm_capitolexposed(row)
            if not tx:
                continue
            when = _parse_date(tx["when"])
            if when and when >= cutoff:
                out.append(tx)
            elif when and when < cutoff:
                stop_early = True
                break
        meta = data.get("meta") or {}
        if stop_early or not meta.get("has_more"):
            break
        page += 1
    return out


def _trade_key(tx: dict) -> tuple:
    return (
        tx.get("symbol", ""),
        (tx.get("politician") or "").lower().strip(),
        tx.get("when", ""),
        int(tx.get("amount_min_usd") or 0),
    )


def _merge_trade_lists(*groups: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for trades in groups:
        for tx in trades:
            key = _trade_key(tx)
            if key in merged:
                cur = merged[key]
                src = set(cur.get("sources") or [])
                src.update(tx.get("sources") or [])
                cur["sources"] = sorted(src)
                if not cur.get("ptr_link") and tx.get("ptr_link"):
                    cur["ptr_link"] = tx["ptr_link"]
            else:
                merged[key] = dict(tx)
    return sorted(merged.values(), key=lambda x: x.get("when", ""), reverse=True)


def _build_buy_clusters(trades: list[dict]) -> list[dict]:
    by_sym: dict[str, list[dict]] = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t)

    clusters: list[dict] = []
    for sym, txs in by_sym.items():
        pols = sorted({t["politician"] for t in txs})
        chambers = sorted({t.get("chamber") or "Congress" for t in txs})
        clusters.append({
            "symbol": sym,
            "politician_count": len(pols),
            "politicians": pols,
            "chambers": chambers,
            "multi_buy": len(pols) >= 2,
            "buy_count": len(txs),
            "latest_when": max(t["when"] for t in txs),
            "max_amount_usd": max(int(t.get("amount_min_usd") or 0) for t in txs),
            "trades": sorted(txs, key=lambda x: x["when"], reverse=True)[:8],
        })

    clusters.sort(
        key=lambda c: (-c["politician_count"], -c["buy_count"], c["latest_when"]),
    )
    return clusters


def fetch_congress_trades(*, lookback_days: int | None = None) -> tuple[list[dict], dict]:
    """Pull qualifying politician stock buys from all live sources."""
    days = lookback_days or lookback_days_default()
    source_stats: dict[str, int | bool] = {}

    cinvests = _fetch_congressinvests(lookback_days=days)
    source_stats["congressinvests"] = len(cinvests)
    source_stats["congressinvests_ok"] = bool(cinvests)

    capitol = _fetch_capitolexposed(lookback_days=days)
    source_stats["capitolexposed"] = len(capitol)
    source_stats["capitolexposed_ok"] = bool(capitol)

    merged = _merge_trade_lists(cinvests, capitol)
    source_stats["merged_buys"] = len(merged)
    return merged, source_stats


def _score_ticker(trades: list[dict], *, lookback_days: int = 90) -> dict:
    cutoff = datetime.now() - timedelta(days=lookback_days)
    buys: list[dict] = []
    politicians: set[str] = set()
    chambers: set[str] = set()
    score = 0.0

    for t in trades:
        if t.get("side") != "buy":
            continue
        when = _parse_date(t.get("when"))
        if not when or when < cutoff:
            continue
        politicians.add(t["politician"])
        chambers.add(t["chamber"])
        recency = max(0.3, 1.0 - (t.get("days_ago", 90) / max(lookback_days, 1)))
        buys.append(t)
        score += t["amount_score"] * 2.5 * recency

    if len(politicians) >= 2:
        score += 6
    if len(politicians) >= 3:
        score += 8
    if {"Senate", "House"}.issubset(chambers):
        score += 10

    score = round(min(100, max(0, score)), 1)
    last_buy = max((b["when"] for b in buys), default="")
    return {
        "congress_edge": score,
        "congress_buys": len(buys),
        "congress_sells": 0,
        "congress_politicians": sorted(politicians),
        "congress_chambers": sorted(chambers),
        "congress_last_buy": last_buy,
        "congress_trades": sorted(buys, key=lambda x: x["when"], reverse=True)[:12],
    }


def build_congress_payload(*, lookback_days: int | None = None) -> dict:
    days = lookback_days or lookback_days_default()
    min_usd = min_buy_usd()
    trades, source_stats = fetch_congress_trades(lookback_days=days)

    by_symbol: dict[str, list[dict]] = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    ticker_edges: dict[str, dict] = {}
    for sym, sym_trades in by_symbol.items():
        ticker_edges[sym] = _score_ticker(sym_trades, lookback_days=90)

    buy_recent = trades[:100]
    buy_clusters = _build_buy_clusters(trades)[:60]
    edge_leaders = sorted(
        (
            {"symbol": sym, **meta}
            for sym, meta in ticker_edges.items()
            if meta["congress_buys"] > 0
        ),
        key=lambda x: (-x["congress_edge"], -x["congress_buys"]),
    )[:40]

    active_sources = [
        name for name in ("congressinvests", "capitolexposed")
        if source_stats.get(f"{name}_ok")
    ]

    return {
        "ok": bool(trades),
        "source": " · ".join(
            s for s in (
                "CongressInvests (Senate EFD + House Clerk PTR)",
                "CapitolExposed (House + Senate filings)",
            )
            if s
        ),
        "sources_active": active_sources,
        "min_buy_usd": min_usd,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "fetched_at_epoch": time.time(),
        "lookback_days": days,
        "total_trades": len(trades),
        "recent_buys": buy_recent,
        "buy_clusters": buy_clusters,
        "edge_leaders": edge_leaders,
        "by_symbol": ticker_edges,
        "stats": {
            "symbols_with_buys": sum(1 for m in ticker_edges.values() if m["congress_buys"] > 0),
            "multi_buy_symbols": sum(1 for c in buy_clusters if c.get("multi_buy")),
            "recent_buy_count": len(buy_recent),
            "senate_trades": sum(1 for t in trades if t.get("chamber") == "Senate"),
            "house_trades": sum(1 for t in trades if t.get("chamber") == "House"),
            "min_buy_usd": min_usd,
            **source_stats,
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
            if data.get("by_symbol") is not None and age <= max_age_sec:
                return data
            if data.get("by_symbol") is not None:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def get_congress_payload(*, refresh: bool = False, lookback_days: int | None = None) -> dict:
    if not refresh:
        cached = load_congress_cache(max_age_sec=CACHE_TTL_SEC)
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
            "stats": {"min_buy_usd": min_buy_usd()},
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
    pols = ", ".join(meta.get("congress_politicians", [])[:2])
    n_pols = len(meta.get("congress_politicians", []))
    if n_pols >= 2:
        note = f"Congress cluster: {n_pols} politicians bought ≥${min_buy_usd():,} · {pols}"
        if "CONGRESS_CLUSTER" not in signals:
            signals.append("CONGRESS_CLUSTER")
    else:
        note = f"Congress buy ≥${min_buy_usd():,}: {meta['congress_buys']} filing(s) · {pols}"
    out["signals"] = signals
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
