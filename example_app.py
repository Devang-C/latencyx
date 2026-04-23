"""
LatencyX example app — FastAPI + SQLAlchemy + httpx, all auto-instrumented.

Run:
    .venv/bin/uvicorn example_app:app --reload

Then hit:
    curl http://localhost:8000/users
    curl http://localhost:8000/users/1/orders
    curl http://localhost:8000/orders/summary
    curl http://localhost:8000/external
    curl http://localhost:8000/custom

Watch traces in your terminal (console exporter) or query the DB:
    sqlite3 -column -header latencyx_traces.db \
        "SELECT span_name, round(duration_ms,2) ms, status_code, trace_id \
         FROM spans ORDER BY started_at DESC LIMIT 20;"
"""

import time

import httpx
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from sqlalchemy import text

import latencyx

# ---------------------------------------------------------------------------
# App + LatencyX
# ---------------------------------------------------------------------------

app = FastAPI()

latencyx.init(
    app=app,
    exporters=["sqlite", "console"],
    time_unit="ms",
    instrument_http_client=True,
    min_duration_ms=0.0,
)

# ---------------------------------------------------------------------------
# Database (SQLite, in-memory for the demo — swap for a real URL in prod)
# ---------------------------------------------------------------------------

engine = sa.create_engine("sqlite:///example_app.db", connect_args={"check_same_thread": False})

# Wire SQLAlchemy — every query becomes a child span linked to the request trace
latencyx.instrument_sqlalchemy(engine)


def _seed_db() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                id   INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
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
        # Only seed if empty
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
    """Fetch user then their orders — shows two db.query child spans in one trace."""
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
    Fetch every user, then query their orders separately.
    LatencyX will record N+2 db.query spans in this trace so you can
    spot the pattern immediately.
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
async def call_external():
    """Outbound HTTP call — traced automatically by the httpx instrumentor."""
    with httpx.Client() as client:
        client.get("https://api.github.com/users/github")
    return {"status": "ok"}


@app.get("/custom")
def custom_trace():
    """Manual instrumentation for a business-logic block."""
    with latencyx.timed(
        "process_report", span_type="business_logic", metadata={"report": "weekly"}
    ):  # noqa: E501
        time.sleep(0.05)
    return {"status": "done"}


@app.get("/slow")
def slow_endpoint():
    """Simulates a slow DB query — useful for testing min_duration_ms filtering."""
    with engine.connect() as conn:
        # Artificial delay simulating a real slow query
        time.sleep(0.2)
        conn.execute(text("SELECT COUNT(*) FROM orders"))
    return {"status": "slow but ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("example_app:app", host="0.0.0.0", port=8000, reload=True)
