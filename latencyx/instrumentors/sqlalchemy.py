import re
import weakref
from typing import Any, Optional

import sqlalchemy.event as sa_event

from ..config import config
from ..core import Span, _current_span_var

# WeakSet tracks instrumented engines without preventing garbage collection.
# When an engine is GC'd its entry is automatically removed, so a new engine
# allocated at the same address is never silently skipped.
_instrumented_engines: weakref.WeakSet[Any] = weakref.WeakSet()

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
    """Attach LatencyX tracing to a SQLAlchemy Engine or AsyncEngine.

    Every query executed through this engine becomes a db.query child span
    linked to the active request span via trace_id / parent_span_id.

    For AsyncEngine, context is propagated via ContextVar — asyncio copies the
    current context when dispatching to thread executors (used by aiosqlite),
    so _current_span_var.get() returns the correct parent span in the event handler.
    """
    # Unwrap AsyncEngine to its underlying sync engine. The cursor events
    # (before_cursor_execute, after_cursor_execute, handle_error) are fired on
    # the sync engine regardless of whether queries originate from async code.
    try:
        from sqlalchemy.ext.asyncio import AsyncEngine

        if isinstance(engine, AsyncEngine):
            engine = engine.sync_engine
    except ImportError:
        pass

    if engine in _instrumented_engines:
        return
    _instrumented_engines.add(engine)

    dialect = engine.dialect.name
    db_url = _sanitize_db_url(engine)

    # Per-connection storage keyed by the connection object's id.
    # Span.start is set in Span.__init__ at the moment _before fires (just before
    # the query executes), so no separate start timestamp is needed here.
    # DB spans intentionally stay off _current_span_var — nested queries appear as
    # siblings of the outer db.query rather than children, which is acceptable for
    # N+1 detection and avoids re-entrancy complexity.
    _inflight: dict[int, Span] = {}

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

        _inflight[id(conn)] = span

    @sa_event.listens_for(engine, "after_cursor_execute")
    def _after(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:  # noqa: E501
        span = _inflight.pop(id(conn), None)
        if span is None:
            return
        span.finish()

    @sa_event.listens_for(engine, "handle_error")
    def _on_error(exception_context: Any) -> None:
        conn = exception_context.connection
        if conn is None:
            return
        span = _inflight.pop(id(conn), None)
        if span is None:
            return
        span.finish(error=exception_context.original_exception)
