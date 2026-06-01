"""Top liquid US stocks and ETFs for scanning."""

from __future__ import annotations

# Major index, sector, thematic, and memory/semiconductor ETFs
TOP_ETFS: list[str] = [
    # Broad market
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "IVV", "RSP",
    # Sector (SPDR + equivalents)
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC",
    "VGT", "VFH", "VDE", "VHT", "VIS", "VCR", "VDC", "VPU",
    # Semiconductors & memory (incl. DRAM thematic)
    "DRAM",   # Roundhill Memory ETF — HBM, NAND, DRAM producers
    "SMH", "SOXX", "XSD", "PSI", "SOXL", "SOXS", "USD", "SSG",
    # AI / tech thematic
    "ARKK", "ARKW", "ARKG", "BOTZ", "ROBO", "AIQ", "IRBO", "SKYY", "HACK", "CIBR",
    # Commodities / bonds / vol (macro context)
    "GLD", "SLV", "USO", "UNG", "TLT", "IEF", "SHY", "HYG", "LQD", "VXX", "UVXY",
    # International / emerging
    "EFA", "EEM", "VEA", "VWO", "FXI", "EWJ", "EWZ", "INDA",
    # Leveraged index (high volume)
    "TQQQ", "SQQQ", "UPRO", "SPXU", "TNA", "TZA",
    # Industry niches
    "XBI", "IBB", "ITB", "XRT", "KRE", "GDX", "GDXJ", "XOP", "OIH", "JETS",
    "ICLN", "TAN", "LIT", "REMX", "COPX",
]

# Curated ~150 most traded / largest US equities (S&P-heavy + popular growth)
TOP_STOCKS: list[str] = [
    # Mega cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "ORCL",
    "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC",
    "SNPS", "CDNS", "PANW", "CRWD", "NOW", "SNOW", "PLTR", "UBER", "ABNB", "DASH",
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
    # Finance
    "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "V", "MA", "PYPL",
    "COF", "USB", "PNC", "TFC", "BK", "ICE", "CME", "SPGI", "MCO",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "ISRG", "VRTX", "REGN", "CVS", "CI", "ELV", "HUM", "MDT",
    # Consumer
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD", "KO", "PEP",
    "PG", "PM", "MO", "CL", "EL", "MDLZ", "KHC", "GIS", "KMB",
    # Industrial / defense
    "CAT", "DE", "GE", "HON", "RTX", "LMT", "NOC", "GD", "BA", "UPS", "FDX",
    "UNP", "CSX", "NSC", "MMM", "EMR", "ITW", "ETN",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",
    # Materials / utilities / REIT sample
    "LIN", "APD", "FCX", "NEM", "NEE", "SO", "DUK", "AEP", "AMT", "PLD", "EQIX",
    # Auto / travel
    "GM", "F", "RIVN", "LCID", "DAL", "UAL", "LUV", "MAR", "HLT", "BKNG", "EXPE",
    # Retail / e-comm / fintech
    "SHOP", "MELI", "SE", "COIN", "HOOD", "SOFI", "AFRM", "ROKU", "ETSY", "EBAY",
    # Semis / AI adjacent
    "ARM", "MRVL", "ON", "ADI", "NXPI", "SMCI", "DELL", "HPE", "IBM", "CSCO",
]


def _merge_symbols(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for s in group:
            s = s.upper().strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def get_universe(source: str = "top_stocks", extra: list[str] | None = None) -> list[str]:
    """Return deduplicated symbol list.

    source:
      - top_stocks: equities only
      - etfs: ETFs only
      - all: stocks + ETFs
      - both: same as all (stocks + ETFs), then merge watchlist from config
      - ourbit: every tokenized stock/ETF on Ourbit (live API + cache)
      - watchlist: extra symbols only
    """
    extra_syms = [s.upper().strip() for s in (extra or []) if s]

    if source == "watchlist":
        return _merge_symbols(extra_syms)

    if source == "ourbit":
        from screener.ourbit_universe import get_ourbit_tickers  # noqa: PLC0415

        base = get_ourbit_tickers()
    elif source == "etfs":
        base = list(TOP_ETFS)
    elif source == "top_stocks":
        base = list(TOP_STOCKS)
    else:
        # all, both, or unknown → full stocks + ETFs
        base = _merge_symbols(TOP_STOCKS, TOP_ETFS)

    if extra_syms:
        return _merge_symbols(base, extra_syms)
    return base
