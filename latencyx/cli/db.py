import sqlite3
import time
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from .formatters import percentile

_err_console = Console(stderr=True)


class LatencyXDB:
    """Read-only SQLite connection with query helpers for CLI commands."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        if not path.exists():
            raise FileNotFoundError(db_path)

        self._conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

    def __enter__(self) -> "LatencyXDB":
        return self

    def __exit__(self, *_: Any) -> None:
        self._conn.close()

    # ── Query methods ───────────────────────────────────────────────────────────

    def get_global_stats(self, since: float) -> dict:
        cur = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors
            FROM spans
            WHERE span_type = 'http.server' AND started_at >= ?
            """,
            (since,),
        )
        row = cur.fetchone()
        total = row["total"] or 0
        errors = row["errors"] or 0

        cur = self._conn.execute(
            """
            SELECT duration_ms FROM spans
            WHERE span_type = 'http.server' AND started_at >= ?
            ORDER BY duration_ms
            """,
            (since,),
        )
        durations = [r[0] for r in cur.fetchall()]
        return {"total": total, "errors": errors, "durations": durations}

    def get_endpoints(self, since: float) -> list:
        cur = self._conn.execute(
            """
            SELECT span_name, duration_ms, error
            FROM spans
            WHERE span_type = 'http.server' AND path IS NOT NULL AND started_at >= ?
            ORDER BY span_name, duration_ms
            """,
            (since,),
        )
        rows = cur.fetchall()

        path_data: dict = defaultdict(lambda: {"durations": [], "errors": 0})
        for row in rows:
            path_data[row["span_name"]]["durations"].append(row["duration_ms"])
            if row["error"]:
                path_data[row["span_name"]]["errors"] += 1

        result = []
        for name, data in path_data.items():
            durations = sorted(data["durations"])
            count = len(durations)
            err = data["errors"]
            result.append(
                {
                    "name": name,
                    "count": count,
                    "p50": percentile(durations, 50),
                    "p95": percentile(durations, 95),
                    "errors": err,
                    "error_rate": (err / count * 100) if count > 0 else 0.0,
                }
            )

        return result

    def get_slowest(
        self,
        limit: int,
        since: float,
        until: Optional[float] = None,
        path: Optional[str] = None,
        status_code: Optional[int] = None,
        span_type: Optional[str] = None,
    ) -> list:
        conditions = ["started_at >= ?"]
        params: list[Any] = [since]

        if until is not None:
            conditions.append("started_at <= ?")
            params.append(until)
        if path:
            conditions.append("(path LIKE ? OR span_name LIKE ?)")
            params.extend([f"%{path}%", f"%{path}%"])
        if status_code is not None:
            conditions.append("status_code = ?")
            params.append(status_code)
        if span_type:
            conditions.append("span_type = ?")
            params.append(span_type)

        params.append(limit)
        where = " AND ".join(conditions)

        cur = self._conn.execute(
            f"""
            SELECT span_name, span_type, duration_ms, status_code, error,
                   started_at, path, method, trace_id
            FROM spans
            WHERE {where}
            ORDER BY duration_ms DESC
            LIMIT ?
            """,  # noqa: S608
            params,
        )
        return cur.fetchall()

    def get_errors(
        self,
        since: float,
        path: Optional[str] = None,
        limit: int = 25,
    ) -> list:
        conditions = ["started_at >= ?", "error IS NOT NULL"]
        params: list[Any] = [since]

        if path:
            conditions.append("(path LIKE ? OR span_name LIKE ?)")
            params.extend([f"%{path}%", f"%{path}%"])

        params.append(limit)
        where = " AND ".join(conditions)

        cur = self._conn.execute(
            f"""
            SELECT COALESCE(path, span_name) AS endpoint, error, COUNT(*) AS count
            FROM spans
            WHERE {where}
            GROUP BY endpoint, error
            ORDER BY count DESC
            LIMIT ?
            """,  # noqa: S608
            params,
        )
        return cur.fetchall()

    def get_trace(self, trace_id: str) -> list:
        cur = self._conn.execute(
            """
            SELECT span_id, parent_span_id, span_name, span_type,
                   duration_ms, status_code, error, started_at
            FROM spans
            WHERE trace_id = ?
            ORDER BY started_at
            """,
            (trace_id,),
        )
        return cur.fetchall()

    def get_traces(
        self,
        since: float,
        path: Optional[str] = None,
        status_code: Optional[int] = None,
        status_range: Optional[tuple[int, int]] = None,
        min_duration: Optional[float] = None,
        limit: int = 50,
    ) -> list:
        conditions = ["span_type = 'http.server'", "started_at >= ?"]
        params: list[Any] = [since]

        if path:
            conditions.append("(path LIKE ? OR span_name LIKE ?)")
            params.extend([f"%{path}%", f"%{path}%"])
        if status_code is not None:
            conditions.append("status_code = ?")
            params.append(status_code)
        elif status_range is not None:
            conditions.append("status_code BETWEEN ? AND ?")
            params.extend(list(status_range))
        if min_duration is not None:
            conditions.append("duration_ms >= ?")
            params.append(min_duration)

        params.append(limit)
        where = " AND ".join(conditions)

        cur = self._conn.execute(
            f"""
            SELECT trace_id, started_at, span_name, path, method,
                   status_code, duration_ms, error
            FROM spans
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT ?
            """,  # noqa: S608
            params,
        )
        return cur.fetchall()

    def get_sparklines(self, since: float, top_n: int = 5) -> dict:
        cur = self._conn.execute(
            """
            SELECT span_name, COUNT(*) AS cnt
            FROM spans
            WHERE span_type = 'http.server' AND started_at >= ?
            GROUP BY span_name
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (since, top_n),
        )
        top_endpoints = [row["span_name"] for row in cur.fetchall()]

        if not top_endpoints:
            return {}

        placeholders = ",".join("?" * len(top_endpoints))
        cur = self._conn.execute(
            f"""
            SELECT span_name, started_at, duration_ms
            FROM spans
            WHERE span_type = 'http.server'
              AND started_at >= ?
              AND span_name IN ({placeholders})
            ORDER BY started_at
            """,  # noqa: S608
            [since, *top_endpoints],
        )
        rows = cur.fetchall()

        now = time.time()
        bucket_size = 3600.0
        num_buckets = 6

        result: dict[str, Any] = {}
        for endpoint in top_endpoints:
            buckets: list[list[float]] = [[] for _ in range(num_buckets)]
            for row in rows:
                if row["span_name"] != endpoint:
                    continue
                age = now - row["started_at"]
                idx = int(age / bucket_size)
                if 0 <= idx < num_buckets:
                    buckets[num_buckets - 1 - idx].append(row["duration_ms"])

            result[endpoint] = {
                "counts": [len(b) for b in buckets],
                "p95": [percentile(sorted(b), 95) for b in buckets],
            }

        return result

    def get_volume(self, since: float, num_buckets: int = 20) -> dict:
        now = time.time()
        bucket_size = max((now - since) / num_buckets, 1.0)
        timestamps = [since + i * bucket_size for i in range(num_buckets)]
        counts: list[int] = [0] * num_buckets
        lat_buckets: list[list[float]] = [[] for _ in range(num_buckets)]

        cur = self._conn.execute(
            """
            SELECT started_at, duration_ms
            FROM spans
            WHERE span_type = 'http.server' AND started_at >= ?
            ORDER BY started_at
            """,
            (since,),
        )
        for row in cur.fetchall():
            idx = int((row["started_at"] - since) / bucket_size)
            idx = max(0, min(num_buckets - 1, idx))
            counts[idx] += 1
            if row["duration_ms"] is not None:
                lat_buckets[idx].append(row["duration_ms"])

        return {
            "timestamps": timestamps,
            "counts": counts,
            "p95": [percentile(sorted(b), 95) for b in lat_buckets],
        }

    def get_span_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM spans")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_db_info(self, recent_window_s: float = 3600.0) -> dict:
        now = time.time()
        cutoff = now - recent_window_s

        total = self.get_span_count()

        cur = self._conn.execute("SELECT MAX(started_at) FROM spans")
        last_seen: Optional[float] = cur.fetchone()[0]

        cur = self._conn.execute("SELECT COUNT(*) FROM spans WHERE started_at >= ?", (cutoff,))
        recent_count: int = cur.fetchone()[0]

        cur = self._conn.execute(
            "SELECT COUNT(*) FROM spans WHERE started_at >= ? AND error IS NOT NULL",
            (cutoff,),
        )
        recent_errors: int = cur.fetchone()[0]

        cur = self._conn.execute(
            """
            SELECT DISTINCT service_name FROM spans
            WHERE service_name IS NOT NULL
            ORDER BY service_name LIMIT 10
            """
        )
        services = [r[0] for r in cur.fetchall()]

        schema_version: Optional[int] = None
        try:
            cur = self._conn.execute("SELECT MAX(version) FROM schema_version")
            schema_version = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass

        return {
            "total_spans": total,
            "last_seen": last_seen,
            "recent_count": recent_count,
            "recent_errors": recent_errors,
            "services": services,
            "schema_version": schema_version,
        }


@contextmanager
def open_db(db_path: str) -> Generator[LatencyXDB, None, None]:
    """CLI-layer wrapper: opens LatencyXDB and prints a friendly error on missing file."""
    import typer

    try:
        with LatencyXDB(db_path) as db:
            yield db
    except FileNotFoundError:
        _err_console.print(f"[red]Error:[/] Database not found: [bold]{db_path}[/]")
        _err_console.print(
            "  Make sure the [bold]sqlite[/] exporter is enabled and your app has run."
        )
        raise typer.Exit(1) from None
