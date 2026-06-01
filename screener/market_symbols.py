"""Index/sector symbols refreshed every live tick (no circular imports)."""

MARKET_TICKERS: list[tuple[str, str]] = [
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq 100"),
    ("IWM", "Russell 2000"),
    ("DIA", "Dow 30"),
    ("VTI", "Total Market"),
    ("XLK", "Technology"),
    ("XLF", "Financials"),
    ("XLE", "Energy"),
    ("XLV", "Healthcare"),
    ("SMH", "Semiconductors"),
    ("DRAM", "Memory"),
    ("GLD", "Gold"),
    ("TLT", "20Y Bonds"),
    ("VIXY", "Volatility"),
]

MARKET_SYMBOLS: list[str] = [sym for sym, _ in MARKET_TICKERS]
