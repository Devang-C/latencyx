import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import config

# Fields that get dedicated columns so the CLI can query them efficiently
# (e.g. WHERE status_code >= 400, GROUP BY path). Everything else is stored
# as JSON in extra_metadata.
_KNOWN_FIELDS = {"method", "path", "status_code", "host", "client", "url"}

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spans (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT    NOT NULL,
    span_name      TEXT    NOT NULL,
    span_type      TEXT    NOT NULL,
    duration_ms    REAL    NOT NULL,
    status         TEXT    NOT NULL,
    error          TEXT,
    traceback      TEXT,
    method         TEXT,
    path           TEXT,
    status_code    INTEGER,
    host           TEXT,
    client         TEXT,
    extra_metadata TEXT
)
"""

_INSERT = """
INSERT INTO spans
    (timestamp, span_name, span_type, duration_ms, status,
     error, traceback, method, path, status_code, host, client, extra_metadata)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteExporter:
    def __init__(self) -> None:
        db_path = Path(config.sqlite_path)
        # Create parent directories if the user pointed to a subdirectory
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False allows the same connection to be used from
        # multiple threads; access is serialised by _lock below.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()

        with self._lock:
            self._conn.execute(_CREATE_TABLE)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        # Ensure the connection is closed if close() was never called explicitly,
        # so Python's GC doesn't emit ResourceWarning on collection.
        try:
            self._conn.close()
        except Exception:
            pass

    def export(self, span: Any) -> None:
        meta = span.metadata or {}

        # Separate known fields (own columns) from overflow metadata (JSON blob)
        extra = {k: v for k, v in meta.items() if k not in _KNOWN_FIELDS}

        row = (
            datetime.now(timezone.utc).isoformat(),
            span.name,
            span.span_type,
            round(span.duration_ms, 3),
            "error" if span.error else "success",
            span.error,
            span.traceback,
            meta.get("method"),
            meta.get("path"),
            meta.get("status_code"),
            meta.get("host"),
            meta.get("client"),
            json.dumps(extra) if extra else None,
        )

        try:
            with self._lock:
                self._conn.execute(_INSERT, row)
                self._conn.commit()
        except sqlite3.Error:
            # Never crash the host app — exporter failures are silent
            pass
