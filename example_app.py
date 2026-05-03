"""
LatencyX example app — FastAPI + SQLAlchemy + httpx + requests, all auto-instrumented.

Run:
    .venv/bin/uvicorn example_app:app --reload

Then hit any of these endpoints:
    curl http://localhost:8000/users
    curl http://localhost:8000/users/1/orders
    curl http://localhost:8000/orders/summary
    curl http://localhost:8000/external
    curl http://localhost:8000/external-requests
    curl http://localhost:8000/custom
    curl http://localhost:8000/slow

Open the dashboard:
    latencyx serve

Check that tracing is working:
    latencyx check
"""

import time

import httpx
import requests
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

import latencyx

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI()

latencyx.init(
    app=app,
    # ── Exporters ────────────────────────────────────────────────────────────
    # "sqlite" (default) writes to a local DB queryable by the CLI and dashboard.
    # Add "console" to log every span to stdout, useful during development.
    # Add "json_file" to emit a JSONL file for log shippers.
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
    # Each instrumentor can be disabled individually if you don't need it
    # or if it conflicts with something in your stack.
    instrument_http_client=True,  # trace outbound httpx calls
    instrument_requests_client=True,  # trace outbound requests library calls
    instrument_sqlalchemy=True,  # trace SQLAlchemy queries (wired below)
    # ── Identity ─────────────────────────────────────────────────────────────
    # Shown in the dashboard sidebar and stored on every span.
    # Useful when multiple services share the same DB.
    service_name="example-api",
    # ── Debugging ────────────────────────────────────────────────────────────
    # include_traceback=True attaches the full Python traceback to error spans.
    # Useful for debugging but increases storage per error span.
    include_traceback=False,
    # ── Kill switch ──────────────────────────────────────────────────────────
    # enabled=False disables all instrumentation entirely with zero overhead.
    # Useful for local dev without any observability overhead.
    # enabled=False,
)

# ---------------------------------------------------------------------------
# Database (SQLite, in-memory for the demo — swap for a real URL in prod)
# ---------------------------------------------------------------------------

engine = sa.create_engine("sqlite:///example_app.db", connect_args={"check_same_thread": False})

# Wire SQLAlchemy — every query becomes a child span linked to the request trace.
# Call this after latencyx.init() and after creating your engine.
latencyx.instrument_sqlalchemy(engine)


def _seed_db() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                id    INTEGER PRIMARY KEY,
                name  TEXT NOT NULL,
                email TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS orders (
                id      INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                item    TEXT NOT NULL,
                amount  REAL NOT NULL
            )
        """)
        )
        if conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 0:
            conn.execute(text("INSERT INTO users VALUES (1,'Alice','alice@example.com')"))
            conn.execute(text("INSERT INTO users VALUES (2,'Bob','bob@example.com')"))
            conn.execute(text("INSERT INTO users VALUES (3,'Carol','carol@example.com')"))
            conn.execute(text("INSERT INTO orders VALUES (1,1,'Widget',9.99)"))
            conn.execute(text("INSERT INTO orders VALUES (2,1,'Gadget',24.99)"))
            conn.execute(text("INSERT INTO orders VALUES (3,2,'Doohickey',4.99)"))
            conn.execute(text("INSERT INTO orders VALUES (4,3,'Thingamajig',14.99)"))
            conn.execute(text("INSERT INTO orders VALUES (5,3,'Whatsit',7.50)"))
            conn.execute(text("INSERT INTO orders VALUES (6,3,'Gizmo',19.99)"))


_seed_db()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/users")
def list_users():
    """Single query — fast and clean."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name, email FROM users")).fetchall()
    return [{"id": r.id, "name": r.name, "email": r.email} for r in rows]


@app.get("/users/{user_id}/orders")
def user_orders(user_id: int):
    """Two queries — shows two db.query child spans in one trace."""
    with engine.connect() as conn:
        user = conn.execute(
            text("SELECT id, name FROM users WHERE id = :id"), {"id": user_id}
        ).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="user not found")

        orders = conn.execute(
            text("SELECT item, amount FROM orders WHERE user_id = :uid"), {"uid": user_id}
        ).fetchall()

    return {
        "user": user.name,
        "orders": [{"item": r.item, "amount": r.amount} for r in orders],
    }


@app.get("/orders/summary")
def orders_summary():
    """
    Classic N+1 demo — intentionally bad.
    Fetches every user then queries their orders one by one.
    LatencyX will record N+2 db.query spans so you can spot the pattern immediately
    in the trace waterfall.
    """
    with engine.connect() as conn:
        users = conn.execute(text("SELECT id, name FROM users")).fetchall()

    result = []
    for user in users:
        with engine.connect() as conn:
            total = conn.execute(
                text("SELECT SUM(amount) FROM orders WHERE user_id = :uid"),
                {"uid": user.id},
            ).scalar()
        result.append({"user": user.name, "total_spent": total or 0})

    return result


@app.get("/external")
async def call_external_httpx():
    """Outbound HTTP via httpx — traced automatically by the httpx instrumentor."""
    with httpx.Client() as client:
        client.get("https://api.github.com/users/github")
    return {"status": "ok", "library": "httpx"}


@app.get("/external-requests")
def call_external_requests():
    """Outbound HTTP via requests — traced automatically by the requests instrumentor."""
    requests.get("https://api.github.com/users/github", timeout=10)
    return {"status": "ok", "library": "requests"}


@app.get("/custom")
def custom_trace():
    """Manual instrumentation for a business-logic block that isn't an HTTP call or DB query."""
    with latencyx.timed("process_report", span_type="generic", metadata={"report": "weekly"}):
        time.sleep(0.05)
    return {"status": "done"}


@app.get("/slow")
def slow_endpoint():
    """Simulates a slow operation — useful for testing min_duration_ms filtering."""
    with engine.connect() as conn:
        time.sleep(0.2)
        conn.execute(text("SELECT COUNT(*) FROM orders"))
    return {"status": "slow but ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("example_app:app", host="0.0.0.0", port=8000, reload=True)
