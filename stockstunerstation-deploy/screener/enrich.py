from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

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

    # Prefer actionable / market-moving headlines
    score = raw + (0.5 if info else 0)
    return score, sentiment


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
    return NewsHeadline(
        title=title.strip(),
        url=url,
        publisher=publisher or "News",
        published=published,
        sentiment=sentiment,
        score=score,
        summary=(summary or "").strip()[:500],
        published_ts=ts,
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


def fetch_news(symbol: str, max_items: int = 3, *, latest_first: bool = True) -> list[NewsHeadline]:
    try:
        raw = _fetch_raw_news(symbol, pull_count=max(12, max_items * 2))
    except Exception:
        return []

    headlines: list[NewsHeadline] = []
    seen_titles: set[str] = set()
    for item in raw:
        parsed = _parse_news_item(item, symbol)
        if not parsed:
            continue
        key = parsed.title.lower()[:80]
        if key in seen_titles:
            continue
        seen_titles.add(key)
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
    """Merge per-symbol headlines into one chronological raw news feed."""
    items: list[dict] = []
    seen: set[str] = set()

    for snap in snapshots:
        for n in snap.news or []:
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
                "published_ts": float(n.get("published_ts") or 0),
                "sentiment": n.get("sentiment", "neutral"),
                "summary": n.get("summary", ""),
            })

    items.sort(key=lambda x: x["published_ts"], reverse=True)
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

    # Chart links are free — set on everyone immediately
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
