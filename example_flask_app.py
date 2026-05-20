"""
LatencyX example app — Flask + httpx + requests, all auto-instrumented.

Run:
    .venv/bin/flask --app example_flask_app run --port 8001

Then hit:
    curl http://localhost:8001/
    curl http://localhost:8001/external
    curl http://localhost:8001/external-requests
    curl http://localhost:8001/custom
    curl http://localhost:8001/items/42

Open the dashboard:
    latencyx serve

Check that tracing is working:
    latencyx check
"""

import time

import httpx
import requests
from flask import Flask, jsonify

import latencyx

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

latencyx.init(
    app=app,
    # ── Exporters ────────────────────────────────────────────────────────────
    # "sqlite" (default) writes to a local DB queryable by the CLI and dashboard.
    # Add "console" to log every span to stdout, useful during development.
    exporters=["sqlite", "console"],
    sqlite_path="latencyx_traces.db",  # where the SQLite DB lives
    # ── Sampling & filtering ─────────────────────────────────────────────────
    # sample_rate: 1.0 = trace everything (default). Use 0.1 in high-traffic
    # production environments to trace 10% of requests with minimal overhead.
    sample_rate=1.0,
    # min_duration_ms: skip exporting spans faster than this threshold.
    # Useful to suppress noise from health checks or trivial operations.
    # Example: min_duration_ms=5.0 ignores anything under 5ms.
    min_duration_ms=0.0,
    # ── Retention ────────────────────────────────────────────────────────────
    # Automatically delete spans older than N days at startup (background thread).
    # Set to None (default) to keep everything. Recommended: 30–90 for dev/staging.
    # retention_days=30,
    # ── Instrumentation toggles ──────────────────────────────────────────────
    instrument_http_client=True,  # trace outbound httpx calls
    instrument_requests_client=True,  # trace outbound requests library calls
    # ── Identity ─────────────────────────────────────────────────────────────
    # Shown in the dashboard sidebar and stored on every span.
    service_name="example-flask-api",
    # ── Debugging ────────────────────────────────────────────────────────────
    # include_traceback=True attaches full Python tracebacks to error spans.
    include_traceback=False,
    # ── Kill switch ──────────────────────────────────────────────────────────
    # enabled=False disables all instrumentation with zero overhead.
    # enabled=False,
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    time.sleep(0.05)
    return jsonify({"hello": "world"})


@app.get("/external")
def call_external_httpx():
    """Outbound HTTP via httpx — traced automatically by the httpx instrumentor."""
    with httpx.Client() as client:
        client.get("https://api.github.com/users/github")
    return jsonify({"status": "ok", "library": "httpx"})


@app.get("/external-requests")
def call_external_requests():
    """Outbound HTTP via requests — traced automatically by the requests instrumentor."""
    requests.get("https://api.github.com/users/github", timeout=10)
    return jsonify({"status": "ok", "library": "requests"})


@app.get("/custom")
def custom_trace():
    """Manual instrumentation for any block of code."""
    with latencyx.timed("custom_operation", span_type="generic"):
        time.sleep(0.1)
    return jsonify({"status": "done"})


@app.get("/items/<int:item_id>")
def get_item(item_id: int):
    """Route template /items/<int:item_id> is recorded, not /items/42."""
    return jsonify({"id": item_id})


if __name__ == "__main__":
    app.run(debug=True, port=8001)
