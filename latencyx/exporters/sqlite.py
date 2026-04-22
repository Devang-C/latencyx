import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import config

# Fields that get dedicated columns so the CLI can query them efficiently.
# Everything else is stored as JSON in extra_metadata.
_KNOWN_FIELDS = {"method", "path", "status_code", "host", "client", "url"}

SCHEMA_VERSION = 2

_CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT    NOT NULL
)
"""

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spans (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT    NOT NULL,     -- ISO8601 UTC (human-readable)
    started_at     REAL    NOT NULL,     -- Unix epoch seconds (fast time-range queries)
    span_name      TEXT    NOT NULL,
    span_type      TEXT    NOT NULL,
    trace_id       TEXT,                 -- shared across all spans in one request
    span_id        TEXT,                 -- unique per span
    parent_span_id TEXT,                 -- span_id of the parent span; null for root spans
    service_name   TEXT,                 -- set via config.service_name
    duration_ms    REAL    NOT NULL,
    status         TEXT    NOT NULL,
    error          TEXT,
    traceback      TEXT,
    method         TEXT,
    path           TEXT,
    status_code    INTEGER,
    host           TEXT,
    client         TEXT,
    url            TEXT,
    extra_metadata TEXT
)
"""

# Indexes covering the access patterns the CLI tools will use.
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_spans_timestamp   ON spans(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_spans_started_at  ON spans(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_spans_duration    ON spans(duration_ms DESC)",
    "CREATE INDEX IF NOT EXISTS idx_spans_trace_id    ON spans(trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_spans_path        ON spans(path)",
    "CREATE INDEX IF NOT EXISTS idx_spans_status_code ON spans(status_code)",
    "CREATE INDEX IF NOT EXISTS idx_spans_service     ON spans(service_name)",
]

_INSERT = """
INSERT INTO spans
    (timestamp, started_at, span_name, span_type, trace_id, span_id, parent_span_id,
     service_name, duration_ms, status, error, traceback,
     method, path, status_code, host, client, url, extra_metadata)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteExporter:
    def __init__(self) -> None:
        db_path = Path(config.sqlite_path)
        # Create parent directories if the user pointed to a subdirectory
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False allows the same connection to be used from
        # multiple threads; writes are serialised by _lock below.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()

        with self._lock:
            # WAL mode gives better write throughput under concurrent access
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
            self._conn.commit()

    def _init_schema(self) -> None:
        """Create the schema on a fresh database and record the version."""
        self._conn.execute(_CREATE_SCHEMA_VERSION_TABLE)

        already_initialised = self._conn.execute("SELECT 1 FROM schema_version LIMIT 1").fetchone()

        if not already_initialised:
            self._conn.execute(_CREATE_TABLE)
            for idx in _INDEXES:
                self._conn.execute(idx)
            self._conn.execute(
                "INSERT INTO schema_version VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )

    def export(self, span: Any) -> None:
        meta = span.metadata or {}

        # Separate known fields (own columns) from overflow metadata (JSON blob)
        extra = {k: v for k, v in meta.items() if k not in _KNOWN_FIELDS}

        started_at: float = getattr(span, "started_at", None) or 0.0
        timestamp = datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat()
        parent = getattr(span, "parent", None)

        row = (
            timestamp,
            started_at,
            span.name,
            span.span_type,
            getattr(span, "trace_id", None),
            getattr(span, "span_id", None),
            getattr(parent, "span_id", None),
            config.service_name,
            round(span.duration_ms, 3),
            "error" if span.error else "success",
            span.error,
            span.traceback,
            meta.get("method"),
            meta.get("path"),
            meta.get("status_code"),
            meta.get("host"),
            meta.get("client"),
            meta.get("url"),
            json.dumps(extra) if extra else None,
        )

        try:
            with self._lock:
                self._conn.execute(_INSERT, row)
                self._conn.commit()
        except sqlite3.Error:
            # Never crash the host app — exporter failures are silent
            pass

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        # Ensure the connection is closed if close() was never called explicitly,
        # so Python's GC doesn't emit ResourceWarning on collection.
        try:
            self._conn.close()
        except Exception:
            pass
