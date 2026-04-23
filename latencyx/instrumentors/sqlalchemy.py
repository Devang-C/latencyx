import re
import time
from typing import Any, Optional

import sqlalchemy.event as sa_event

from ..config import config
from ..core import Span, _current_span_var

# DML: INSERT INTO <table>, UPDATE <table>, DELETE FROM <table>
_DML_RE = re.compile(r"^\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM|DELETE)\s+(\w+)", re.IGNORECASE)
# DDL: CREATE/DROP/ALTER [TABLE|INDEX|VIEW|DATABASE] <name>
_DDL_RE = re.compile(
    r"^\s*(CREATE|DROP|ALTER)\s+(?:TABLE|INDEX|VIEW|DATABASE\s+)?\s*(\w+)", re.IGNORECASE
)
# SELECT: table name lives after the FROM keyword
_SELECT_FROM_RE = re.compile(r"\bFROM\s+(\w+)", re.IGNORECASE)
# Stored procedure calls
_CALL_RE = re.compile(r"^\s*(CALL|EXEC(?:UTE)?)\b", re.IGNORECASE)


def _span_name_from_sql(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        return "db.query"

    upper = sql[:10].upper()

    if upper.startswith("SELECT"):
        m = _SELECT_FROM_RE.search(sql)
        return f"SELECT {m.group(1)}" if m else "SELECT"

    m = _DML_RE.match(sql)
    if m:
        op = m.group(1).split()[0].upper()  # "INSERT INTO" → "INSERT"
        return f"{op} {m.group(2)}"

    m = _DDL_RE.match(sql)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"

    m = _CALL_RE.match(sql)
    if m:
        return m.group(1).upper()

    return "db.query"


def _sanitize_db_url(engine: Any) -> str:
    """Return db URL with credentials stripped."""
    url = engine.url
    return str(url.render_as_string(hide_password=True))


def instrument_sqlalchemy(engine: Any) -> None:
    """Attach LatencyX tracing to a SQLAlchemy Engine.

    Every query executed through this engine becomes a db.query child span
    linked to the active request span via trace_id / parent_span_id.
    """
    dialect = engine.dialect.name
    db_url = _sanitize_db_url(engine)

    # Per-connection storage keyed by the connection object's id.
    # Stores (Span, perf_counter start) for the in-flight query.
    _inflight: dict[int, tuple[Span, float]] = {}

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _before(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:  # noqa: E501
        if not config.enabled:
            return

        parent: Optional[Span] = _current_span_var.get()
        span = Span(_span_name_from_sql(statement), span_type="db.query")
        span.parent = parent
        if parent is not None:
            span.trace_id = parent.trace_id

        span.metadata["dialect"] = dialect
        span.metadata["db_url"] = db_url
        span.metadata["sql"] = statement

        if config.sqlalchemy_capture_params:
            span.metadata["params"] = str(parameters)

        _inflight[id(conn)] = (span, time.perf_counter())

    @sa_event.listens_for(engine, "after_cursor_execute")
    def _after(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:  # noqa: E501
        entry = _inflight.pop(id(conn), None)
        if entry is None:
            return
        span, t0 = entry
        span.start = t0  # align with how Span.finish() computes duration
        span.finish()

    @sa_event.listens_for(engine, "handle_error")
    def _on_error(exception_context: Any) -> None:
        conn = exception_context.connection
        if conn is None:
            return
        entry = _inflight.pop(id(conn), None)
        if entry is None:
            return
        span, t0 = entry
        span.start = t0
        span.finish(error=exception_context.original_exception)
