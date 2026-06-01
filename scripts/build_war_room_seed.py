#!/usr/bin/env python3
"""Build data/gold_war_room_seed.json for instant Render load (cloud-fast analysis)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["RENDER"] = "true"

from screener.cache_io import save_war_room_seed  # noqa: E402
from screener.gold_war_room import run_war_room_analysis  # noqa: E402

OUT = ROOT / "data" / "gold_war_room_seed.json"


def main() -> None:
    payload = run_war_room_analysis()
    if not payload.get("ok"):
        print("ERROR:", payload.get("error"))
        sys.exit(1)
    agents = payload.get("agents") or {}
    save_war_room_seed(payload)
    print(f"Wrote {OUT} — {len(agents)} agents, bias={payload.get('market_bias', {}).get('bias')}")
    print(f"Rows: {len((payload.get('agent_consensus') or {}).get('rows', []))}")


if __name__ == "__main__":
    main()
