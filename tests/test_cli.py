import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
from typer.testing import CliRunner

from latencyx.cli import app
from latencyx.cli.formatters import fmt_dur, parse_since, percentile
from latencyx.exporters.sqlite import (
    _CREATE_SCHEMA_VERSION_TABLE,
    _CREATE_TABLE,
    _INDEXES,
    SCHEMA_VERSION,
)

runner = CliRunner()

# ─── DB fixture ────────────────────────────────────────────────────────────────

TRACE_ID = "trace123abc456def789"
ROOT_SPAN_ID = "rootspan1111111111"
CHILD_SPAN_1 = "childspan111111111"
CHILD_SPAN_2 = "childspan222222222"


def _make_schema(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_SCHEMA_VERSION_TABLE)
    conn.execute(_CREATE_TABLE)
    for idx in _INDEXES:
        conn.execute(idx)
    conn.execute(
        "INSERT INTO schema_version VALUES (?, ?)",
        (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _insert(
    conn: sqlite3.Connection,
    span_name: str,
    span_type: str,
    duration_ms: float,
    path: Optional[str] = None,
    method: Optional[str] = None,
    status_code: int = 200,
    error: Optional[str] = None,
    started_at: Optional[float] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
) -> None:
    if started_at is None:
        started_at = time.time() - 3600  # 1 hour ago, well within 24h default
    sid = span_id or uuid.uuid4().hex
    tid = trace_id or uuid.uuid4().hex
    ts = datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat()
    status = "error" if error else "success"
    conn.execute(
        """
        INSERT INTO spans
            (timestamp, started_at, span_name, span_type, trace_id, span_id, parent_span_id,
             service_name, duration_ms, status, error, traceback,
             method, path, status_code, host, client, url, extra_metadata)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ts,
            started_at,
            span_name,
            span_type,
            tid,
            sid,
            parent_span_id,
            "test-service",
            duration_ms,
            status,
            error,
            None,
            method,
            path,
            status_code,
            None,
            None,
            None,
            None,
        ),
    )
    conn.commit()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "test.db"
    conn = sqlite3.connect(str(path))
    _make_schema(conn)

    # GET /api/users — 4 success + 1 error
    for dur in [10.0, 20.0, 30.0, 40.0]:
        _insert(conn, "GET /api/users", "http.server", dur, path="/api/users", method="GET")
    _insert(
        conn,
        "GET /api/users",
        "http.server",
        500.0,
        path="/api/users",
        method="GET",
        status_code=500,
        error="InternalError: timeout",
    )

    # POST /api/orders — 2 success + 1 error
    _insert(conn, "POST /api/orders", "http.server", 50.0, path="/api/orders", method="POST")
    _insert(conn, "POST /api/orders", "http.server", 200.0, path="/api/orders", method="POST")
    _insert(
        conn,
        "POST /api/orders",
        "http.server",
        800.0,
        path="/api/orders",
        method="POST",
        status_code=500,
        error="ConnectionRefused: db offline",
    )

    # Trace root + 2 DB children
    _insert(
        conn,
        "GET /api/detail",
        "http.server",
        45.2,
        path="/api/detail",
        method="GET",
        status_code=200,
        trace_id=TRACE_ID,
        span_id=ROOT_SPAN_ID,
    )
    _insert(
        conn,
        "SELECT * FROM items WHERE id = ?",
        "db.query",
        12.1,
        trace_id=TRACE_ID,
        span_id=CHILD_SPAN_1,
        parent_span_id=ROOT_SPAN_ID,
    )
    _insert(
        conn,
        "SELECT * FROM cache WHERE key = ?",
        "db.query",
        8.3,
        trace_id=TRACE_ID,
        span_id=CHILD_SPAN_2,
        parent_span_id=ROOT_SPAN_ID,
    )

    # Old span — 48 h ago, outside the default 24 h window
    _insert(
        conn,
        "GET /api/old",
        "http.server",
        100.0,
        path="/api/old",
        method="GET",
        started_at=time.time() - 48 * 3600,
    )

    conn.close()
    return str(path)


@pytest.fixture
def empty_db(tmp_path: Path) -> str:
    path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(path))
    _make_schema(conn)
    conn.close()
    return str(path)


# ─── Formatter unit tests ───────────────────────────────────────────────────────


def test_fmt_dur_ms():
    assert fmt_dur(12.34) == "12.34ms"
    assert fmt_dur(123.4) == "123.4ms"


def test_fmt_dur_seconds():
    assert fmt_dur(1500.0) == "1.50s"


def test_percentile_empty():
    assert percentile([], 95) is None


def test_percentile_single():
    assert percentile([42.0], 95) == 42.0
    assert percentile([42.0], 50) == 42.0


def test_percentile_accuracy():
    vals = list(range(1, 101))  # 1..100, sorted
    # Allow ±1 tolerance — index-based percentile is approximate at small N
    assert 49 <= (percentile(vals, 50) or 0) <= 51
    assert 94 <= (percentile(vals, 95) or 0) <= 96
    assert 98 <= (percentile(vals, 99) or 0) <= 100


def test_parse_since_relative():
    before = time.time()
    result = parse_since("1h")
    after = time.time()
    assert before - 3600 - 1 <= result <= after - 3600 + 1


def test_parse_since_iso():
    result = parse_since("2024-01-15T00:00:00")
    assert result == datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp()


# ─── Missing DB ────────────────────────────────────────────────────────────────


def test_missing_db_exits_with_error(tmp_path: Path):
    result = runner.invoke(app, ["stats", "--db", str(tmp_path / "no.db")])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ─── stats ─────────────────────────────────────────────────────────────────────


def test_stats_request_count(db_path: str):
    result = runner.invoke(app, ["stats", "--db", db_path])
    assert result.exit_code == 0
    # 5 users + 3 orders + 1 detail = 9 HTTP server spans within 24h
    assert "9" in result.output


def test_stats_shows_error_info(db_path: str):
    result = runner.invoke(app, ["stats", "--db", db_path])
    assert result.exit_code == 0
    assert "errors" in result.output.lower()


def test_stats_shows_percentiles(db_path: str):
    result = runner.invoke(app, ["stats", "--db", db_path])
    assert result.exit_code == 0
    assert "p50" in result.output
    assert "p95" in result.output
    assert "p99" in result.output


def test_stats_no_data(empty_db: str):
    result = runner.invoke(app, ["stats", "--db", empty_db])
    assert result.exit_code == 0
    assert "no data" in result.output.lower()


# ─── endpoints ─────────────────────────────────────────────────────────────────


def test_endpoints_lists_paths(db_path: str):
    result = runner.invoke(app, ["endpoints", "--db", db_path])
    assert result.exit_code == 0
    assert "/api/users" in result.output
    assert "/api/orders" in result.output


def test_endpoints_old_span_excluded(db_path: str):
    result = runner.invoke(app, ["endpoints", "--db", db_path])
    assert result.exit_code == 0
    assert "/api/old" not in result.output


def test_endpoints_no_data(empty_db: str):
    result = runner.invoke(app, ["endpoints", "--db", empty_db])
    assert result.exit_code == 0
    assert "no endpoint data" in result.output.lower()


def test_endpoints_sort_invalid(db_path: str):
    result = runner.invoke(app, ["endpoints", "--db", db_path, "--sort", "badvalue"])
    assert result.exit_code != 0  # click.Choice returns exit code 2 for invalid values


# ─── slowest ───────────────────────────────────────────────────────────────────


def test_slowest_top_is_800ms(db_path: str):
    result = runner.invoke(app, ["slowest", "--db", db_path])
    assert result.exit_code == 0
    # POST /api/orders has the 800ms span — it should appear before GET /api/users
    orders_pos = result.output.find("POST /api/orders")
    users_pos = result.output.find("GET /api/users")
    assert orders_pos != -1
    assert orders_pos < users_pos


def test_slowest_filter_by_path(db_path: str):
    result = runner.invoke(app, ["slowest", "--db", db_path, "--path", "/api/orders"])
    assert result.exit_code == 0
    assert "/api/orders" in result.output or "POST /api/orders" in result.output
    assert "/api/users" not in result.output


def test_slowest_limit(db_path: str):
    result = runner.invoke(app, ["slowest", "--db", db_path, "--limit", "2"])
    assert result.exit_code == 0
    lines = [ln for ln in result.output.splitlines() if "ms" in ln or ".s" in ln.lower()]
    assert len(lines) <= 3  # at most limit + possible header row


def test_slowest_no_match(db_path: str):
    result = runner.invoke(app, ["slowest", "--db", db_path, "--path", "/nonexistent"])
    assert result.exit_code == 0
    assert "no traces" in result.output.lower()


# ─── errors ────────────────────────────────────────────────────────────────────


def test_errors_shows_both_error_types(db_path: str):
    result = runner.invoke(app, ["errors", "--db", db_path])
    assert result.exit_code == 0
    assert "InternalError" in result.output or "timeout" in result.output
    assert "ConnectionRefused" in result.output or "offline" in result.output


def test_errors_filter_by_path(db_path: str):
    result = runner.invoke(app, ["errors", "--db", db_path, "--path", "/api/orders"])
    assert result.exit_code == 0
    assert "ConnectionRefused" in result.output or "offline" in result.output


def test_errors_no_errors(empty_db: str):
    result = runner.invoke(app, ["errors", "--db", empty_db])
    assert result.exit_code == 0
    assert "no errors" in result.output.lower()


# ─── trace ─────────────────────────────────────────────────────────────────────


def test_trace_renders_tree(db_path: str):
    result = runner.invoke(app, ["trace", TRACE_ID, "--db", db_path])
    assert result.exit_code == 0
    assert "GET /api/detail" in result.output
    assert "SELECT * FROM items" in result.output
    assert "SELECT * FROM cache" in result.output


def test_trace_shows_span_count(db_path: str):
    result = runner.invoke(app, ["trace", TRACE_ID, "--db", db_path])
    assert result.exit_code == 0
    assert "3 spans" in result.output


def test_trace_not_found(db_path: str):
    result = runner.invoke(app, ["trace", "nonexistenttraceid", "--db", db_path])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ─── report ────────────────────────────────────────────────────────────────────


def test_report_has_summary_panel(db_path: str):
    result = runner.invoke(app, ["report", "--db", db_path, "--since", "24h"])
    assert result.exit_code == 0
    assert "LatencyX Report" in result.output


def test_report_has_slow_endpoints_section(db_path: str):
    result = runner.invoke(app, ["report", "--db", db_path, "--since", "24h"])
    assert result.exit_code == 0
    assert "Slow Endpoints" in result.output


def test_report_has_errors_section(db_path: str):
    result = runner.invoke(app, ["report", "--db", db_path, "--since", "24h"])
    assert result.exit_code == 0
    assert "Recent Errors" in result.output


def test_report_no_data(empty_db: str):
    result = runner.invoke(app, ["report", "--db", empty_db, "--since", "24h"])
    assert result.exit_code == 0


# ─── LatencyXDB.get_volume ──────────────────────────────────────────────────────


def test_get_volume_returns_correct_structure(db_path: str):
    from latencyx.cli.db import LatencyXDB

    since = time.time() - 3600
    with LatencyXDB(db_path) as db:
        result = db.get_volume(since)

    assert "timestamps" in result
    assert "counts" in result
    assert "p95" in result
    assert len(result["timestamps"]) == 20
    assert len(result["counts"]) == 20
    assert len(result["p95"]) == 20


def test_get_volume_counts_http_server_spans(db_path: str):
    from latencyx.cli.db import LatencyXDB

    since = time.time() - 7200
    with LatencyXDB(db_path) as db:
        result = db.get_volume(since)

    assert sum(result["counts"]) > 0


def test_get_volume_empty_db_returns_zeros(empty_db: str):
    from latencyx.cli.db import LatencyXDB

    since = time.time() - 3600
    with LatencyXDB(empty_db) as db:
        result = db.get_volume(since)

    assert sum(result["counts"]) == 0
    # buckets with no data return None from percentile()
    assert all(v is None for v in result["p95"])  # type: ignore[misc]
