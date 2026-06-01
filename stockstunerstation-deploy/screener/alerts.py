from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

AlertType = Literal[
    "price_above",
    "price_below",
    "change_above",
    "change_below",
    "volume_above",
    "unusual_score_above",
]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "alerts.json"


@dataclass
class PriceAlert:
    id: str
    symbol: str
    alert_type: AlertType
    value: float
    enabled: bool = True
    note: str = ""
    created_at: str = ""
    triggered_at: str | None = None
    triggered_value: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlertStore:
    alerts: list[PriceAlert] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"alerts": [a.to_dict() for a in self.alerts]}


def _path(p: Path | None) -> Path:
    p = p or DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_alerts(path: Path | None = None) -> AlertStore:
    fp = _path(path)
    if not fp.exists():
        return AlertStore()
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
        alerts = []
        for item in raw.get("alerts", []):
            alerts.append(PriceAlert(**item))
        return AlertStore(alerts=alerts)
    except (json.JSONDecodeError, TypeError, KeyError):
        return AlertStore()


def save_alerts(store: AlertStore, path: Path | None = None) -> None:
    fp = _path(path)
    fp.write_text(json.dumps(store.to_dict(), indent=2), encoding="utf-8")


def create_alert(
    symbol: str,
    alert_type: AlertType,
    value: float,
    note: str = "",
    path: Path | None = None,
) -> PriceAlert:
    store = load_alerts(path)
    alert = PriceAlert(
        id=str(uuid.uuid4())[:8],
        symbol=symbol.upper().strip(),
        alert_type=alert_type,
        value=float(value),
        note=note.strip(),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    store.alerts.append(alert)
    save_alerts(store, path)
    return alert


def delete_alert(alert_id: str, path: Path | None = None) -> bool:
    store = load_alerts(path)
    before = len(store.alerts)
    store.alerts = [a for a in store.alerts if a.id != alert_id]
    if len(store.alerts) < before:
        save_alerts(store, path)
        return True
    return False


def _check_one(alert: PriceAlert, quote: dict, stock: dict | None) -> bool:
    if not alert.enabled or alert.triggered_at:
        return False

    price = quote.get("price") or (stock or {}).get("price")
    change = quote.get("change_pct") if quote.get("change_pct") is not None else (stock or {}).get("change_pct")
    vol_ratio = quote.get("volume_ratio") or (stock or {}).get("volume_ratio")
    unusual = (stock or {}).get("unusual_score", 0)

    triggered = False
    tv = None

    if alert.alert_type == "price_above" and price is not None and price >= alert.value:
        triggered, tv = True, price
    elif alert.alert_type == "price_below" and price is not None and price <= alert.value:
        triggered, tv = True, price
    elif alert.alert_type == "change_above" and change is not None and change >= alert.value:
        triggered, tv = True, change
    elif alert.alert_type == "change_below" and change is not None and change <= alert.value:
        triggered, tv = True, change
    elif alert.alert_type == "volume_above" and vol_ratio is not None and vol_ratio >= alert.value:
        triggered, tv = True, vol_ratio
    elif alert.alert_type == "unusual_score_above" and unusual >= alert.value:
        triggered, tv = True, unusual

    if triggered:
        alert.triggered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert.triggered_value = round(float(tv), 4) if tv is not None else None
    return triggered


def evaluate_alerts(
    quotes: dict[str, dict],
    stocks_by_sym: dict[str, dict] | None = None,
    path: Path | None = None,
) -> list[dict]:
    """Check all enabled alerts; persist triggers; return newly triggered."""
    store = load_alerts(path)
    stocks_by_sym = stocks_by_sym or {}
    newly: list[dict] = []

    for alert in store.alerts:
        if alert.symbol not in quotes and alert.symbol not in stocks_by_sym:
            continue
        quote = quotes.get(alert.symbol, {})
        stock = stocks_by_sym.get(alert.symbol)
        if _check_one(alert, quote, stock):
            newly.append(alert.to_dict())

    if newly:
        save_alerts(store, path)
    return newly
