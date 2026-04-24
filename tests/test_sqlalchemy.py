from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import latencyx
from latencyx.config import config


def make_engine(**init_kwargs):
    """In-memory SQLite engine — no external DB needed."""
    engine = sa.create_engine("sqlite:///:memory:")
    latencyx.init(exporters=["console"], instrument_http_client=False, **init_kwargs)
    latencyx.instrument_sqlalchemy(engine)
    return engine


@pytest.fixture(autouse=True)
def dispose_engines():
    """Dispose all SQLAlchemy engines created during a test to avoid ResourceWarnings."""
    engines: list = []
    _orig_create = sa.create_engine

    def _tracked_create(*args, **kwargs):
        e = _orig_create(*args, **kwargs)
        engines.append(e)
        return e

    sa.create_engine = _tracked_create  # type: ignore[assignment]
    yield
    sa.create_engine = _orig_create  # type: ignore[assignment]
    for e in engines:
        e.dispose()


# ---------------------------------------------------------------------------
# Span shape
# ---------------------------------------------------------------------------


def test_query_produces_db_query_span():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    spans = [c.args[0] for c in mock_export.call_args_list]
    db_spans = [s for s in spans if s.span_type == "db.query"]
    assert len(db_spans) == 1


def test_span_name_select():
    # No FROM clause (scalar select) → just "SELECT"
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert db_spans[0].name == "SELECT"


def test_span_name_select_with_table(tmp_path):
    engine = sa.create_engine("sqlite:///:memory:")
    latencyx.init(exporters=["console"], instrument_http_client=False)
    latencyx.instrument_sqlalchemy(engine)

    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.commit()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT id, name FROM users WHERE id = 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 1
    assert db_spans[0].name == "SELECT users"


def test_span_records_sql():
    engine = make_engine()
    sql = "SELECT 42"

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text(sql))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert db_spans[0].metadata["sql"] == sql


def test_span_records_dialect():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert db_spans[0].metadata["dialect"] == "sqlite"


def test_span_records_db_url():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert "sqlite" in db_spans[0].metadata["db_url"]


def test_span_has_duration():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert db_spans[0].duration_ms is not None
    assert db_spans[0].duration_ms >= 0.0


# ---------------------------------------------------------------------------
# Trace linking
# ---------------------------------------------------------------------------


def test_db_span_inherits_trace_id_from_parent():
    """Query span must share trace_id with the active request span."""
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with latencyx.timed("request", span_type="http.server") as req_span:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

    all_spans = [c.args[0] for c in mock_export.call_args_list]
    db_spans = [s for s in all_spans if s.span_type == "db.query"]

    assert req_span is not None
    assert len(db_spans) == 1
    assert db_spans[0].trace_id == req_span.trace_id
    assert db_spans[0].parent is req_span


def test_db_span_without_parent_gets_own_trace_id():
    """Query outside a request context starts its own trace."""
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert db_spans[0].parent is None
    assert db_spans[0].trace_id is not None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_span_records_query_error():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT * FROM nonexistent_table"))
            except Exception:
                pass

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 1
    assert db_spans[0].error is not None


# ---------------------------------------------------------------------------
# Config guards
# ---------------------------------------------------------------------------


def test_params_not_captured_by_default():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT :val").bindparams(val=42))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert "params" not in db_spans[0].metadata


def test_params_captured_when_enabled():
    engine = sa.create_engine("sqlite:///:memory:")
    latencyx.init(
        exporters=["console"],
        instrument_http_client=False,
        sqlalchemy_capture_params=True,
    )
    latencyx.instrument_sqlalchemy(engine)

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT :val").bindparams(val=42))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert "params" in db_spans[0].metadata


def test_disabled_skips_tracing():
    engine = sa.create_engine("sqlite:///:memory:")
    latencyx.init(exporters=["console"], instrument_http_client=False)
    latencyx.instrument_sqlalchemy(engine)

    with patch("latencyx.exporters.export_span") as mock_export:
        config.enabled = False
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 0


def test_instrument_sqlalchemy_flag_false_skips():
    """instrument_sqlalchemy=False on config means instrument_sqlalchemy() is a no-op."""
    engine = sa.create_engine("sqlite:///:memory:")
    latencyx.init(
        exporters=["console"],
        instrument_http_client=False,
        instrument_sqlalchemy=False,
    )
    latencyx.instrument_sqlalchemy(engine)

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 0


def test_multiple_queries_produce_multiple_spans():
    engine = make_engine()

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT 2"))
            conn.execute(text("SELECT 3"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 3


# ---------------------------------------------------------------------------
# Span name extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("SELECT * FROM orders", "SELECT orders"),
        ("select * from users", "SELECT users"),
        ("SELECT 1", "SELECT"),
        ("INSERT INTO payments (id) VALUES (1)", "INSERT payments"),
        ("INSERT INTO sessions VALUES (?)", "INSERT sessions"),
        ("UPDATE users SET name = ?", "UPDATE users"),
        ("DELETE FROM audit_log WHERE id = ?", "DELETE audit_log"),
        ("CREATE TABLE foo (id INT)", "CREATE foo"),
        ("DROP TABLE foo", "DROP foo"),
        ("CALL some_proc()", "CALL"),
        ("", "db.query"),
    ],
)
def test_span_name_extraction(sql, expected):
    from latencyx.instrumentors.sqlalchemy import _span_name_from_sql

    assert _span_name_from_sql(sql) == expected


# ---------------------------------------------------------------------------
# AsyncEngine support
# ---------------------------------------------------------------------------


@pytest.fixture
def async_engine():
    """In-memory aiosqlite engine instrumented for async tracing."""
    import asyncio

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    latencyx.init(exporters=["console"], instrument_http_client=False)
    latencyx.instrument_sqlalchemy(engine)
    yield engine
    asyncio.run(engine.dispose())


@pytest.mark.asyncio
async def test_async_query_produces_db_query_span(async_engine):
    with patch("latencyx.exporters.export_span") as mock_export:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 1


@pytest.mark.asyncio
async def test_async_db_span_inherits_trace_id_from_parent(async_engine):
    """Query span must share trace_id with the active request span in async context."""
    with patch("latencyx.exporters.export_span") as mock_export:
        with latencyx.timed("request", span_type="http.server") as req_span:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

    all_spans = [c.args[0] for c in mock_export.call_args_list]
    db_spans = [s for s in all_spans if s.span_type == "db.query"]

    assert req_span is not None
    assert len(db_spans) == 1
    assert db_spans[0].trace_id == req_span.trace_id
    assert db_spans[0].parent is req_span


@pytest.mark.asyncio
async def test_async_span_records_query_error(async_engine):
    with patch("latencyx.exporters.export_span") as mock_export:
        async with async_engine.connect() as conn:
            try:
                await conn.execute(text("SELECT * FROM nonexistent_table"))
            except Exception:
                pass

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 1
    assert db_spans[0].error is not None


@pytest.mark.asyncio
async def test_async_disabled_skips_tracing(async_engine):
    with patch("latencyx.exporters.export_span") as mock_export:
        config.enabled = False
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 0


@pytest.mark.asyncio
async def test_async_multiple_queries_produce_multiple_spans(async_engine):
    with patch("latencyx.exporters.export_span") as mock_export:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT 2"))
            await conn.execute(text("SELECT 3"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 3


def test_double_instrumentation_is_idempotent():
    """Instrumenting the same engine twice must not register duplicate listeners."""
    engine = sa.create_engine("sqlite:///:memory:")
    latencyx.init(exporters=["console"], instrument_http_client=False)
    latencyx.instrument_sqlalchemy(engine)
    latencyx.instrument_sqlalchemy(engine)  # second call is a no-op

    with patch("latencyx.exporters.export_span") as mock_export:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    db_spans = [c.args[0] for c in mock_export.call_args_list if c.args[0].span_type == "db.query"]
    assert len(db_spans) == 1


def test_async_engine_and_sync_engine_share_no_duplicate_listeners():
    """Instrumenting AsyncEngine then its sync_engine directly is a no-op — one listener set."""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine as cae

    from latencyx.instrumentors.sqlalchemy import _instrumented_engines

    async_eng = cae("sqlite+aiosqlite:///:memory:")
    sync_eng = async_eng.sync_engine

    latencyx.init(exporters=["console"], instrument_http_client=False)

    assert sync_eng not in _instrumented_engines
    latencyx.instrument_sqlalchemy(async_eng)
    assert sync_eng in _instrumented_engines

    # Second call (direct sync_engine) must be a no-op — guard prevents double-registration.
    latencyx.instrument_sqlalchemy(sync_eng)
    assert len(list(_instrumented_engines)) == 1

    asyncio.run(async_eng.dispose())
