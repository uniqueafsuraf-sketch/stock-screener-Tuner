"""Kill stale listeners and pick a free port for the dashboard."""

from __future__ import annotations

import socket
import subprocess
import sys
import time

APP_VERSION = "4.1"
PREFERRED_PORT = 5050
FALLBACK_PORTS = (8765, 5051, 8080)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def kill_port_listeners(port: int) -> None:
    """Stop any process listening on *port* (Windows)."""
    if sys.platform != "win32":
        return
    ps = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen "
        f"-ErrorAction SilentlyContinue | ForEach-Object {{ "
        f"Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        check=False,
    )
    # netstat fallback (older Windows / no Get-NetTCPConnection)
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout or ""
        for line in out.splitlines():
            if f":{port}" not in line or "LISTENING" not in line:
                continue
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit():
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True,
                        check=False,
                    )
    except OSError:
        pass


def resolve_port(preferred: int = PREFERRED_PORT) -> int:
    """Free *preferred* if possible; otherwise use the first free fallback port."""
    kill_port_listeners(preferred)
    time.sleep(1.5)
    if _port_free(preferred):
        return preferred

    print(f"WARNING: Port {preferred} is still in use (often an old dashboard).")
    print("Trying alternate ports…")
    for port in FALLBACK_PORTS:
        kill_port_listeners(port)
        time.sleep(0.5)
        if _port_free(port):
            return port

    raise SystemExit(
        f"Could not bind a port ({preferred} or {FALLBACK_PORTS}). "
        "Close other dashboard windows and run start_dashboard.bat again."
    )
