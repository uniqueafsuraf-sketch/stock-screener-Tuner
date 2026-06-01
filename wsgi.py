"""Production entry point (Render, Railway, VPS + gunicorn)."""

from dashboard.server import app, init_production

# Light init only — heavy scan starts in a background thread
init_production()

application = app
