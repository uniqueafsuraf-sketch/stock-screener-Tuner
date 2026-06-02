#!/usr/bin/env python3
"""Run before pushing to GitHub — checks files Render needs at repo root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    "wsgi.py",
    "requirements.txt",
    "runtime.txt",
    "render.yaml",
    "config.yaml",
    "dashboard/server.py",
    "screener/__init__.py",
    "data/seed_bootstrap.json",
    "data/ourbit_stocks.json",
    "data/gold_war_room_seed.json",
]

RECOMMENDED = [
    "dashboard/templates/index.html",
    "dashboard/static/dashboard.js",
    "dashboard/static/gold_war_room.js",
]


def main() -> int:
    print(f"Checking deploy layout in:\n  {ROOT}\n")
    ok = True
    for rel in REQUIRED:
        path = ROOT / rel
        if path.is_file():
            print(f"  OK  {rel}")
        else:
            print(f"  MISSING  {rel}")
            ok = False
    for rel in RECOMMENDED:
        path = ROOT / rel
        if not path.is_file():
            print(f"  WARN  optional missing: {rel}")
    if not ok:
        print("\nFix missing files, then push again.")
        print("Render Root Directory must be EMPTY (repo root = folder with wsgi.py).")
        return 1
    try:
        sys.path.insert(0, str(ROOT))
        from wsgi import application  # noqa: F401
        print("\n  OK  wsgi imports successfully")
    except Exception as e:
        print(f"\n  FAIL  wsgi import: {e}")
        return 1
    print("\nReady to push to GitHub and deploy on Render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
