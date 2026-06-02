from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import yfinance as yf

from screener.models import StockSnapshot

# Simple headline scoring (no external NLP deps)
BULLISH = re.compile(
    r"\b(beat|beats|surge|soar|rally|jump|jumps|upgrade|upgraded|bullish|record|"
    r"growth|profit|gains|gain|raises|raised|guidance|outperform|buy rating|"
    r"approval|approved|breakout|high|contract win|partnership|dividend hike|"
    r"buyback|expansion|strong demand|top pick)\b",
    re.I,
)
BEARISH = re.compile(
    r"\b(miss|misses|plunge|crash|fall|falls|downgrade|downgraded|bearish|"
    r"layoff|lawsuit|probe|investigation|warning|cut guidance|recall|"
    r"bankruptcy|fraud|selloff|weak demand|disappoint)\b",
    re.I,
)
INFORMATIVE = re.compile(
    r"\b(earnings|revenue|FDA|merger|acquisition|IPO|guidance|forecast|"
    r"fed|rate|inflation|tariff|deal|contract|launch|product|CEO|"
    r"quarter|Q[1-4]|annual|dividend|split|SEC|analyst)\b",
    re.I,
)

_NAME_STRIP = re.compile(r"\b(inc\.?|corp\.?|corporation|company|co\.?|ltd\.?|plc|group)\b", re.I)


def _news_cfg() -> dict:
    try:
        from screener.scan import load_config  # noqa: PLC0415

        return load_config().get("news") or {}
    except Exception:
        return {}


def max_news_age_hours() -> int:
    return int(_news_cfg().get("max_age_hours", 48))


def require_symbol_mention() -> bool:
    return bool(_news_cfg().get("require_symbol_mention", True))


@dataclass
class NewsHeadline:
    title: str
    url: str
    publisher: str
    published: str
    sentiment: str  # bullish | bearish | neutral
    score: float
    summary: str = ""
    published_ts: float = 0.0
    mentions_symbol: bool = True

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "publisher": self.publisher,
            "published": self.published,
            "sentiment": self.sentiment,
            "score": self.score,
            "summary": self.summary,
            "published_ts": self.published_ts,
            "mentions_symbol": self.mentions_symbol,
        }


def chart_links(symbol: str) -> dict[str, str]:
    sym = symbol.upper().strip()
    return {
        "tradingview": f"https://www.tradingview.com/chart/?symbol={sym}",
        "yahoo": f"https://finance.yahoo.com/quote/{sym}/chart/",
        "finviz": f"https://finviz.com/quote.ashx?t={sym}",
        "yahoo_news": f"https://finance.yahoo.com/quote/{sym}/news/",
    }


def score_headline(title: str) -> tuple[float, str]:
    """Higher score = more relevant bullish/informative for traders."""
    t = title or ""
    bull = len(BULLISH.findall(t))
    bear = len(BEARISH.findall(t))
    info = len(INFORMATIVE.findall(t))

    raw = bull * 2.0 + info * 1.0 - bear * 2.5
    if bull > bear and bull > 0:
        sentiment = "bullish"
    elif bear > bull and bear > 0:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    score = raw + (0.5 if info else 0)
    return score, sentiment


@lru_cache(maxsize=512)
def _company_aliases(symbol: str) -> tuple[str, ...]:
    sym = symbol.upper().strip()
    aliases: set[str] = {sym}
    try:
        info = yf.Ticker(sym).info or {}
        for key in ("shortName", "longName", "displayName"):
            name = (info.get(key) or "").strip()
            if len(name) >= 3:
                aliases.add(name)
                cleaned = _NAME_STRIP.sub("", name).strip(" ,.-")
                if len(cleaned) >= 4:
                    aliases.add(cleaned)
    except Exception:
        pass
    return tuple(sorted(aliases, key=len, reverse=True))


def headline_mentions_symbol(symbol: str, title: str, summary: str = "") -> bool:
    """True when headline text clearly references the ticker or company name."""
    sym = symbol.upper().strip()
    if not sym:
        return False
    blob_u = f"{title or ''} {summary or ''}".upper()

    for alias in _company_aliases(sym):
        alias_u = alias.upper()
        if len(alias_u) >= 4 and alias_u in blob_u:
            return True

    if len(sym) >= 3:
        if re.search(rf"\b{re.escape(sym)}\b", blob_u):
            return True
        if re.search(rf"\({re.escape(sym)}\)", blob_u):
            return True
        if re.search(rf"\${re.escape(sym)}\b", blob_u):
            return True
        return False

    if re.search(rf"\({re.escape(sym)}\)", blob_u):
        return True
    if re.search(rf"\${re.escape(sym)}\b", blob_u):
        return True
    if re.search(rf"\b{re.escape(sym)}\s+(stock|shares|earnings)\b", blob_u):
        return True
    return False


def _parse_news_item(item: dict, symbol: str = "") -> NewsHeadline | None:
    """Handle yfinance news payload variants."""
    title = ""
    url = ""
    publisher = ""
    summary = ""
    pub_ts = None

    if "content" in item and isinstance(item["content"], dict):
        c = item["content"]
        title = c.get("title") or ""
        summary = c.get("summary") or c.get("description") or ""
        pub_ts = c.get("pubDate") or c.get("displayTime")
        prov = c.get("provider") or {}
        publisher = prov.get("displayName") or prov.get("name") or ""
        canon = c.get("canonicalUrl") or c.get("clickThroughUrl") or {}
        if isinstance(canon, dict):
            url = canon.get("url") or ""
        elif isinstance(canon, str):
            url = canon
    else:
        title = item.get("title") or ""
        url = item.get("link") or item.get("url") or ""
        publisher = item.get("publisher") or item.get("source") or ""
        summary = item.get("summary") or ""
        pub_ts = item.get("providerPublishTime") or item.get("published")

    if not title:
        return None

    if not url and symbol:
        url = f"https://finance.yahoo.com/quote/{symbol.upper()}/news/"

    published = _format_date(pub_ts)
    ts = _parse_timestamp(pub_ts)
    score, sentiment = score_headline(title)
    mentions = headline_mentions_symbol(symbol, title, summary) if symbol else True
    return NewsHeadline(
        title=title.strip(),
        url=url,
        publisher=publisher or "News",
        published=published,
        sentiment=sentiment,
        score=score,
        summary=(summary or "").strip()[:500],
        published_ts=ts,
        mentions_symbol=mentions,
    )


def _parse_timestamp(pub_ts) -> float:
    if pub_ts is None:
        return 0.0
    try:
        if isinstance(pub_ts, (int, float)):
            return float(pub_ts)
        s = str(pub_ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError, OSError):
        return 0.0


def _format_date(pub_ts) -> str:
    if pub_ts is None:
        return ""
    try:
        ts = _parse_timestamp(pub_ts)
        if ts <= 0:
            return str(pub_ts)[:16]
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return str(pub_ts)[:16]


def _fetch_raw_news(symbol: str, pull_count: int = 15) -> list[dict]:
    ticker = yf.Ticker(symbol)
    try:
        raw = ticker.get_news(count=pull_count, tab="news") or []
    except Exception:
        raw = []
    if not raw:
        try:
            raw = ticker.news or []
        except Exception:
            raw = []
    return raw[:pull_count]


def _passes_news_filters(symbol: str, headline: NewsHeadline) -> bool:
    max_age = max_news_age_hours() * 3600
    now = time.time()
    if headline.published_ts > 0 and headline.published_ts < now - max_age:
        return False
    if require_symbol_mention() and not headline_mentions_symbol(
        symbol, headline.title, headline.summary
    ):
        return False
    return True


def fetch_news(symbol: str, max_items: int = 3, *, latest_first: bool = True) -> list[NewsHeadline]:
    try:
        raw = _fetch_raw_news(symbol, pull_count=max(16, max_items * 4))
    except Exception:
        return []

    headlines: list[NewsHeadline] = []
    seen_titles: set[str] = set()
    for item in raw:
        parsed = _parse_news_item(item, symbol)
        if not parsed or not _passes_news_filters(symbol, parsed):
            continue
        key = parsed.title.lower()[:80]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        parsed.mentions_symbol = True
        headlines.append(parsed)

    if latest_first:
        headlines.sort(key=lambda h: h.published_ts, reverse=True)
    else:
        headlines.sort(key=lambda h: (h.score, h.sentiment == "bullish"), reverse=True)
    return headlines[:max_items]


def build_news_wire(
    snapshots: list[StockSnapshot],
    *,
    max_total: int = 200,
) -> list[dict]:
    """Merge per-symbol headlines into one chronological verified news feed."""
    items: list[dict] = []
    seen: set[str] = set()
    max_age = max_news_age_hours() * 3600
    now = time.time()

    for snap in snapshots:
        for n in snap.news or []:
            ts = float(n.get("published_ts") or 0)
            if ts > 0 and ts < now - max_age:
                continue
            if require_symbol_mention() and not n.get("mentions_symbol", True):
                continue
            url = (n.get("url") or "").strip()
            key = url or f"{snap.symbol}:{(n.get('title') or '')[:60]}"
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "symbol": snap.symbol,
                "title": n.get("title", ""),
                "url": url,
                "publisher": n.get("publisher", ""),
                "published": n.get("published", ""),
                "published_ts": ts,
                "sentiment": n.get("sentiment", "neutral"),
                "summary": n.get("summary", ""),
                "mentions_symbol": True,
            })

    items.sort(key=lambda x: x["published_ts"], reverse=True)
    return items[:max_total]


def build_live_news_wire(
    symbols: list[str],
    *,
    max_total: int | None = None,
    max_headlines: int | None = None,
    workers: int | None = None,
) -> list[dict]:
    """Fetch fresh verified headlines for many symbols (live news poll)."""
    cfg = _news_cfg()
    max_total = max_total or int(cfg.get("wire_max_total", 150))
    max_headlines = max_headlines or int(cfg.get("max_headlines", 4))
    workers = workers or int(cfg.get("workers", 12))

    items: list[dict] = []
    seen: set[str] = set()

    def _pull(sym: str) -> list[dict]:
        headlines = fetch_news(sym, max_items=max_headlines, latest_first=True)
        out: list[dict] = []
        for h in headlines:
            d = h.to_dict()
            d["symbol"] = sym.upper()
            out.append(d)
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_pull, sym): sym for sym in symbols if sym}
        for fut in as_completed(futures):
            try:
                batch = fut.result()
            except Exception:
                continue
            for n in batch:
                url = (n.get("url") or "").strip()
                key = url or f"{n.get('symbol')}:{(n.get('title') or '')[:60]}"
                if key in seen:
                    continue
                seen.add(key)
                items.append(n)

    items.sort(key=lambda x: float(x.get("published_ts") or 0), reverse=True)
    return items[:max_total]


def enrich_snapshot(snap: StockSnapshot, max_news: int = 2) -> None:
    snap.chart_links = chart_links(snap.symbol)
    headlines = fetch_news(snap.symbol, max_items=max_news, latest_first=True)
    snap.news = [h.to_dict() for h in headlines]


def enrich_all(
    snapshots: list[StockSnapshot],
    *,
    max_news: int = 2,
    workers: int = 12,
    only_opportunities: bool = False,
    latest_first: bool = True,
) -> None:
    targets = [s for s in snapshots if s.has_opportunity] if only_opportunities else snapshots

    for snap in snapshots:
        snap.chart_links = chart_links(snap.symbol)
        if snap not in targets:
            snap.news = []

    def _work(snap: StockSnapshot) -> tuple[str, list[dict]]:
        headlines = fetch_news(snap.symbol, max_items=max_news, latest_first=latest_first)
        return snap.symbol, [h.to_dict() for h in headlines]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_work, s): s for s in targets}
        by_sym = {}
        for fut in as_completed(futures):
            sym, news = fut.result()
            by_sym[sym] = news

    for snap in targets:
        snap.news = by_sym.get(snap.symbol, [])
