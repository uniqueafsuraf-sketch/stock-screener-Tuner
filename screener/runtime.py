"""Host environment detection (local vs cloud deploy)."""

from __future__ import annotations

import os


def is_cloud_host() -> bool:
    """True on Render, Railway, Heroku, etc."""
    if os.environ.get("RENDER") == "true":
        return True
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return True
    if os.environ.get("DYNO"):
        return True
    # Render/Heroku set PORT; local dev uses 127.0.0.1 via flask dev server
    if os.environ.get("PORT") and not os.environ.get("STS_LOCAL"):
        return True
    return False
