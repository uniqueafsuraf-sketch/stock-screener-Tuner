#!/usr/bin/env python3
"""Launch StocksTunerStation dashboard."""

from __future__ import annotations

import sys
import time
import webbrowser

from dashboard.launch import APP_VERSION, resolve_port
from dashboard.server import main


def _wait_for_health(port: int, timeout: float = 25.0) -> bool:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.4)
    return False


if __name__ == "__main__":
    port = resolve_port()
    url = f"http://127.0.0.1:{port}"

    if "--no-browser" not in sys.argv:
        import threading

        def _open_when_ready() -> None:
            if _wait_for_health(port):
                webbrowser.open(url)

        threading.Thread(target=_open_when_ready, daemon=True).start()

    from dashboard.brand import SITE_NAME

    print(f"{SITE_NAME} v{APP_VERSION} on {url}")
    main(port=port)
