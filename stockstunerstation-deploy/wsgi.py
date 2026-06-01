"""Production entry point (Render, Railway, VPS + gunicorn)."""

from dashboard.server import app, init_production

init_production()

application = app
