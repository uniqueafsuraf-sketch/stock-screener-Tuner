from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from screener.enrich import chart_links
from screener.signals import Opportunity


def _chart_links_cell(symbol: str, links: dict | None) -> str:
    L = links or chart_links(symbol)
    parts = []
    for label, key in [("TV", "tradingview"), ("Yahoo", "yahoo"), ("Finviz", "finviz"), ("News", "yahoo_news")]:
        url = L.get(key, "")
        if url:
            parts.append(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{label}</a>')
    return " · ".join(parts)


def _news_cell(news: list[dict]) -> str:
    if not news:
        return '<span class="muted">—</span>'
    bits = []
    for n in news:
        title = html.escape(n.get("title", ""))
        url = html.escape(n.get("url", "#"))
        sent = n.get("sentiment", "neutral")
        bits.append(
            f'<div class="news-{sent}"><span class="badge">{sent}</span> '
            f'<a href="{url}" target="_blank" rel="noopener">{title}</a></div>'
        )
    return "".join(bits)


def to_console(opportunities: list[Opportunity]) -> str:
    if not opportunities:
        return "No opportunities matched your criteria right now.\n"

    lines = [
        f"{'SYMBOL':<8} {'PRICE':>8} {'CHG%':>7} {'VOLx':>6} {'RSI':>5}  SIGNALS",
        "-" * 72,
    ]
    for o in opportunities:
        rsi_s = f"{o.rsi:.0f}" if o.rsi is not None else "—"
        lines.append(
            f"{o.symbol:<8} ${o.price:>7.2f} {o.change_pct:>+6.1f}% "
            f"{o.volume_ratio:>5.1f}x {rsi_s:>5}  {' + '.join(o.signals) or '-'}"
        )
        for note in o.notes:
            lines.append(f"         > {note}")
        if o.news:
            for n in o.news[:1]:
                lines.append(f"         > NEWS [{n.get('sentiment')}]: {n.get('title', '')[:70]}")
        lines.append("")
    return "\n".join(lines)


def to_html(opportunities: list[Opportunity], out_path: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = ""
    for o in opportunities:
        signal_tags = "".join(
            f'<span class="tag">{html.escape(s.replace("_", " "))}</span>' for s in o.signals
        )
        notes = "<br>".join(html.escape(n) for n in o.notes) if o.notes else "—"
        chg_class = "up" if o.change_pct >= 0 else "down"
        rows += f"""
        <tr>
          <td><span class="mono" style="font-weight:600">{html.escape(o.symbol)}</span><br>{_chart_links_cell(o.symbol, o.chart_links)}</td>
          <td class="mono">${o.price:,.2f}</td>
          <td><span class="chg {chg_class}">{o.change_pct:+.2f}%</span></td>
          <td class="mono">{o.volume_ratio:.1f}×</td>
          <td class="mono">{o.rsi:.1f}</td>
          <td class="mono">{o.score}</td>
          <td>{signal_tags}</td>
          <td class="notes">{notes}</td>
          <td class="news">{_news_cell(o.news)}</td>
        </tr>"""

    empty = (
        '<tr><td colspan="9" class="empty">No setups found. '
        "Try lowering thresholds in config.yaml.</td></tr>"
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>StocksTunerStation — Report</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
  <style>
    :root {{ font-family: "DM Sans", system-ui, sans-serif; background: #0c1222; color: #fff; font-size: 18px; }}
    body {{ max-width: 1280px; margin: 0 auto; padding: 2rem 1.5rem; }}
    .header {{ margin-bottom: 1.5rem; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; letter-spacing: -0.03em; }}
    .meta {{ color: #5c6d82; font-size: 0.85rem; margin-top: 0.35rem; }}
    .panel {{ border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; overflow: hidden; background: #111820; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.8125rem; }}
    th, td {{ padding: 0.7rem 1rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); vertical-align: top; }}
    th {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #5c6d82; background: #0e1219; }}
    .mono {{ font-family: "JetBrains Mono", monospace; font-variant-numeric: tabular-nums; }}
    a {{ color: #4f8cff; text-decoration: none; font-size: 0.75rem; margin-right: 0.35rem; }}
    a:hover {{ text-decoration: underline; }}
    .tag {{ display: inline-block; padding: 0.12rem 0.4rem; border-radius: 4px; font-size: 0.62rem; font-weight: 600; text-transform: uppercase; margin: 0.1rem; background: rgba(79,140,255,0.15); color: #7dd3fc; }}
    .chg {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-family: "JetBrains Mono", monospace; font-weight: 600; font-size: 0.8rem; }}
    .chg.up {{ color: #001a0d; background: #00ff88; font-size: 1.1rem; padding: 0.35rem 0.65rem; box-shadow: 0 0 12px rgba(0,255,136,0.4); }}
    .chg.down {{ color: #fff; background: #ff4466; font-size: 1.1rem; padding: 0.35rem 0.65rem; box-shadow: 0 0 12px rgba(255,68,102,0.4); }}
    .notes, .news {{ color: #8b9cb3; font-size: 0.78rem; line-height: 1.4; }}
    .empty {{ text-align: center; padding: 3rem; color: #5c6d82; }}
    .footer {{ margin-top: 1.5rem; font-size: 0.78rem; color: #5c6d82; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>StocksTunerStation</h1>
    <p class="meta">Report generated {ts} · {len(opportunities)} active setup(s)</p>
  </div>
  <div class="panel">
  <table>
    <thead>
      <tr>
        <th>Symbol</th><th>Price</th><th>Change</th><th>Volume</th>
        <th>RSI</th><th>Score</th><th>Signals</th><th>Analysis</th><th>Headlines</th>
      </tr>
    </thead>
    <tbody>{rows if opportunities else empty}</tbody>
  </table>
  </div>
  <p class="footer">
    Charts: TV · Yahoo · Finviz · News. Headlines scored bullish / bearish / neutral by keywords.
    <em>Not financial advice.</em> Open the live dashboard for 1-second quote updates.
  </p>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
