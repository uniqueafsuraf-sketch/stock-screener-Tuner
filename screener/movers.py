"""Top gainers / losers by change % for the live header tape."""

from __future__ import annotations

TOP_N = 15


def top_gainers_losers(
    stocks: list[dict],
    quotes: dict[str, dict] | None = None,
    *,
    top_n: int = TOP_N,
) -> tuple[list[dict], list[dict]]:
    """Return gainers (change > 0) and losers (change < 0), sorted by change %."""
    quotes = quotes or {}
    rows: list[dict] = []

    for row in stocks:
        sym = (row.get("symbol") or "").upper().strip()
        if not sym:
            continue
        q = quotes.get(sym, {})
        chg = q.get("change_pct") if q.get("change_pct") is not None else row.get("change_pct")
        price = q.get("price") if q.get("price") is not None else row.get("price")
        if chg is None:
            continue
        chg_f = float(chg)
        rows.append({
            "symbol": sym,
            "label": sym,
            "price": round(float(price or 0), 2),
            "change_pct": round(chg_f, 2),
        })

    if not rows and quotes:
        for sym, q in quotes.items():
            chg = q.get("change_pct")
            if chg is None:
                continue
            rows.append({
                "symbol": sym,
                "label": sym,
                "price": round(float(q.get("price") or 0), 2),
                "change_pct": round(float(chg), 2),
            })

    gainers = sorted(
        [r for r in rows if r["change_pct"] > 0],
        key=lambda x: x["change_pct"],
        reverse=True,
    )[:top_n]

    losers = sorted(
        [r for r in rows if r["change_pct"] < 0],
        key=lambda x: x["change_pct"],
    )[:top_n]

    for r in gainers:
        r["role"] = "gainer"
    for r in losers:
        r["role"] = "loser"

    return gainers, losers


def movers_tape_list(
    stocks: list[dict],
    quotes: dict[str, dict] | None = None,
    *,
    top_n: int = TOP_N,
) -> list[dict]:
    """Gainers first (best %), then losers (worst %)."""
    gainers, losers = top_gainers_losers(stocks, quotes, top_n=top_n)
    return gainers + losers
