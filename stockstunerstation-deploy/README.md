# StocksTunerStation

Live stock scanners and market flow. Scans a watchlist for setups you care about:

- **Volume spikes** — today’s volume vs 20-day average
- **Sell-offs** — sharp down days on elevated volume (+ optional RSI oversold)
- **Trendlines** — price near support/resistance built from swing highs/lows
- **Combined setups** — e.g. sell-off into support, volume into resistance

## Quick start (Windows — easiest)

1. Open the `stock-screener` folder
2. **Double-click `START.bat`**
3. First run installs everything; then your browser opens automatically

Read **`GETTING_STARTED.txt`** if anything fails.

Advanced (command line):

```bash
cd stock-screener
install.bat
start_dashboard.bat
```

Open the URL printed in the terminal — usually **http://127.0.0.1:5050** (or **8765** if an old server was still using 5050).

If you see **“URL not found”** or a blank page: close every old terminal/Python window, run `start_dashboard.bat` again, and use the **new** URL from that window — not a bookmarked tab.

Health check: **http://127.0.0.1:5050/api/health** should return JSON with `"version": "2.0"`.

### Put it online (free website)

See **[GO_LIVE_FREE.md](GO_LIVE_FREE.md)** — deploy free on Render (`https://your-app.onrender.com`).

Own domain + VPS: **[DEPLOY.md](DEPLOY.md)**.

### Scanner features

| Feature | What it does |
|---------|----------------|
| **Edge Score (0–100)** | Ranks every symbol: setups + volume + RS vs SPY + gaps + news + risk/reward |
| **Edge HQ** | Top-ranked trade ideas with letter grades (A+ to C) |
| **Trade thesis** | Auto-generated one-liner: what to watch and why |
| **Market tape** | Live SPY, QQQ, IWM, sectors |
| **Gap scanner** | Opening gaps vs prior close |
| **Rel strength** | 5-day performance vs SPY |
| **Earnings watch** | Reports within 14 days |
| **News wire** | Bullish-ranked headlines in side panel |
| **Gainers / Losers / Unusual vol** | Fast mover panels |

Each row includes **chart links** (TradingView, Yahoo, Finviz) and **latest headlines** ranked for bullish / market-moving context. Use the **News feed** tab for a combined view.

**Live data:** Price, change %, and volume refresh **every second** via Server-Sent Events. Full setup scan (signals, trendlines, news) refreshes every 5 minutes (configurable).

CLI-only report:

```bash
python run.py
```

Opens `output/opportunities.html`.

## Customize

Edit `config.yaml`:

| Setting | What it does |
|--------|----------------|
| `universe` | `top_stocks`, `etfs`, `all`, `both` (stocks + ~80 ETFs incl. **DRAM**, SMH, SOXX) |
| `watchlist` | Extra symbols merged into the scan |
| `volume_spike_ratio` | Min volume multiple (default 1.8x) |
| `selloff_min_pct` | Min single-day drop % (e.g. -2.5) |
| `trendline_proximity_pct` | How close price must be to trendline |
| `min_avg_dollar_volume` | Filters illiquid names |

## Signals explained

| Signal | Meaning |
|--------|---------|
| `VOLUME_SPIKE` | Unusual participation today |
| `SELLOFF` | Big down move on volume |
| `OVERSOLD` | RSI below threshold during sell-off |
| `AT_SUPPORT` | Price at rising support trendline |
| `AT_RESISTANCE` | Price at resistance trendline |
| `SELLOFF_AT_SUPPORT` | Capitulation into support — reversal watch |
| `BREAKOUT_SETUP` | Volume + price testing resistance |

## Data

Uses [Yahoo Finance](https://pypi.org/project/yfinance/) (free, delayed). For live alerts or full-market scans, you can later plug in Polygon, Alpaca, or IBKR.

## Disclaimer

For research and education only. Not financial advice.
