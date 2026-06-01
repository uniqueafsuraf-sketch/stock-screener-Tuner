from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

import yfinance as yf

from screener.market_symbols import MARKET_SYMBOLS
from screener.runtime import is_cloud_host

CHUNK_SIZE = 25 if is_cloud_host() else 45
MAX_WORKERS = 6 if is_cloud_host() else 24
PRIORITY_SYMBOLS: list[str] = MARKET_SYMBOLS


@dataclass
class LiveQuote:
    symbol: str
    price: float
    change_pct: float
    volume: int
    avg_volume: int
    volume_ratio: float
    market_time: int = 0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "avg_volume": self.avg_volume,
            "volume_ratio": self.volume_ratio,
            "market_time": self.market_time,
        }


@dataclass
class LiveState:
    quotes: dict[str, LiveQuote] = field(default_factory=dict)
    updated_at: float = 0.0
    updated_at_str: str = ""
    tick: int = 0
    error: str | None = None
    fetching: bool = False

    def to_dict(self) -> dict:
        return {
            "quotes": {k: v.to_dict() for k, v in self.quotes.items()},
            "updated_at": self.updated_at_str,
            "tick": self.tick,
            "error": self.error,
            "fetching": self.fetching,
            "count": len(self.quotes),
        }


def _quote_from_fast_info(symbol: str) -> LiveQuote | None:
    try:
        fi = yf.Ticker(symbol).fast_info
        price = _num(fi.get("lastPrice"))
        if price is None:
            return None
        prev = _num(fi.get("regularMarketPreviousClose")) or _num(fi.get("previousClose"))
        chg_pct = 0.0
        if prev and prev > 0:
            chg_pct = ((price - prev) / prev) * 100

        vol = int(_num(fi.get("lastVolume")) or _num(fi.get("regularMarketVolume")) or 0)
        avg_vol = int(
            _num(fi.get("tenDayAverageVolume"))
            or _num(fi.get("threeMonthAverageVolume"))
            or 0
        )
        vol_ratio = round(vol / avg_vol, 2) if avg_vol > 0 else 0.0

        return LiveQuote(
            symbol=symbol,
            price=round(price, 2),
            change_pct=round(chg_pct, 2),
            volume=vol,
            avg_volume=avg_vol,
            volume_ratio=vol_ratio,
            market_time=int(time.time()),
        )
    except Exception:
        return None


def fetch_live_quotes(symbols: list[str]) -> dict[str, LiveQuote]:
    """Fetch real-time quotes via yfinance (parallel)."""
    out: dict[str, LiveQuote] = {}
    symbols = [s.upper().strip() for s in symbols if s.strip()]
    if not symbols:
        return out

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_quote_from_fast_info, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            q = fut.result()
            if q:
                out[q.symbol] = q
    return out


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


class LiveEngine:
    """Background quote poller — updates a rotating chunk every interval."""

    def __init__(self, interval_sec: float = 1.0) -> None:
        self.interval_sec = interval_sec
        self._symbols: list[str] = []
        self._chunk_index = 0
        self._state = LiveState()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy = False

    def set_symbols(self, symbols: list[str]) -> None:
        with self._lock:
            self._symbols = list(dict.fromkeys(s.upper() for s in symbols))

    def get_payload(self) -> dict:
        with self._lock:
            return self._state.to_dict()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="live-quotes")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _next_chunk(self) -> list[str]:
        with self._lock:
            symbols = self._symbols
            if not symbols:
                return []
            start = self._chunk_index * CHUNK_SIZE
            chunk = symbols[start : start + CHUNK_SIZE]
            self._chunk_index += 1
            if start + CHUNK_SIZE >= len(symbols):
                self._chunk_index = 0
            return chunk

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            chunk = self._next_chunk()
            # Market indices + memory/semis refresh every tick; rotate rest of universe
            batch = list(dict.fromkeys(PRIORITY_SYMBOLS + chunk))

            if batch and not self._busy:
                self._busy = True
                with self._lock:
                    self._state.fetching = True
                try:
                    fresh = fetch_live_quotes(batch)
                    now = time.time()
                    with self._lock:
                        self._state.quotes.update(fresh)
                        self._state.updated_at = now
                        self._state.updated_at_str = datetime.now().strftime("%H:%M:%S")
                        self._state.tick += 1
                        self._state.error = None
                except Exception as e:
                    with self._lock:
                        self._state.error = str(e)
                finally:
                    with self._lock:
                        self._state.fetching = False
                    self._busy = False

            elapsed = time.time() - t0
            wait = max(0.05, self.interval_sec - elapsed)
            self._stop.wait(wait)


def merge_live_into_stock(stock: dict, quote: LiveQuote | None) -> dict:
    if not quote:
        return stock
    stock = dict(stock)
    stock["price"] = quote.price
    stock["change_pct"] = quote.change_pct
    stock["volume_ratio"] = quote.volume_ratio
    stock["live_volume"] = quote.volume
    stock["live"] = True
    return stock
