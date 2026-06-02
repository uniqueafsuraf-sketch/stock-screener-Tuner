from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class StockSnapshot:
    symbol: str
    price: float
    change_pct: float
    volume_ratio: float
    rsi: float
    score: int = 0
    signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    support_dist_pct: float | None = None
    resistance_dist_pct: float | None = None
    avg_dollar_volume_m: float = 0.0
    has_opportunity: bool = False
    chart_links: dict[str, str] = field(default_factory=dict)
    news: list[dict] = field(default_factory=list)
    # Pro / edge fields
    edge_score: float = 0.0
    edge_grade: str = "—"
    thesis: str = ""
    gap_pct: float | None = None
    vs_spy_5d: float | None = None
    momentum_5d: float | None = None
    week52_position: float | None = None
    risk_reward: float | None = None
    earnings_within_days: int | None = None
    session: str = "regular"
    unusual_activity: list[str] = field(default_factory=list)
    unusual_score: float = 0.0
    dollar_volume_m: float = 0.0
    on_ourbit: bool = False
    ourbit_symbol: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signal_summary"] = " + ".join(self.signals) if self.signals else ""
        d["unusual_summary"] = " + ".join(self.unusual_activity) if self.unusual_activity else ""
        return d


@dataclass
class ScanResult:
    scanned_at: str
    symbols_scanned: int
    opportunities: list[StockSnapshot]
    all_stocks: list[StockSnapshot]
    stats: dict
    edge_plays: list[dict] = field(default_factory=list)
    gainers: list[dict] = field(default_factory=list)
    losers: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    high_rvol: list[dict] = field(default_factory=list)
    rel_strength: list[dict] = field(default_factory=list)
    earnings_watch: list[dict] = field(default_factory=list)
    market_pulse: list[dict] = field(default_factory=list)
    proprietary_signals: list[dict] = field(default_factory=list)
    unusual_activity: list[dict] = field(default_factory=list)
    news_wire: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scanned_at": self.scanned_at,
            "symbols_scanned": self.symbols_scanned,
            "stats": self.stats,
            "opportunities": [o.to_dict() for o in self.opportunities],
            "all_stocks": [s.to_dict() for s in self.all_stocks],
            "edge_plays": self.edge_plays,
            "gainers": self.gainers,
            "losers": self.losers,
            "gaps": self.gaps,
            "high_rvol": self.high_rvol,
            "rel_strength": self.rel_strength,
            "unusual_activity": self.unusual_activity,
            "earnings_watch": self.earnings_watch,
            "market_pulse": self.market_pulse,
            "proprietary_signals": self.proprietary_signals,
            "news_wire": self.news_wire,
        }
