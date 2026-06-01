#!/usr/bin/env python3
"""Run the stock opportunity screener."""

from __future__ import annotations

import argparse
from pathlib import Path

from screener.report import to_console, to_html
from screener.scan import scan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan for volume spikes, sell-offs, and trendline setups."
    )
    parser.add_argument(
        "-c", "--config", default="config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output/opportunities.html",
        help="HTML report path",
    )
    parser.add_argument("--no-html", action="store_true", help="Skip HTML report")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config not found: {config_path}")

    print("Scanning watchlist for opportunities...\n")
    opportunities = scan(config_path=str(config_path))

    print(to_console(opportunities))
    print(f"Found {len(opportunities)} symbol(s) with active setups.\n")

    if not args.no_html:
        out = to_html(opportunities, Path(args.output))
        print(f"HTML report: {out.resolve()}")


if __name__ == "__main__":
    main()
