from __future__ import annotations

from importlib.resources import files as _pkg_files
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .cli.db import LatencyXDB
from .cli.formatters import parse_since, percentile

_SLOW_MS = 200.0


def _load_ui() -> str:
    return _pkg_files("latencyx.ui").joinpath("index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_since_http(s: str) -> float:
    try:
        return parse_since(s)
    except Exception:
        raise HTTPException(
            400, f"Invalid time range: {s!r}. Use '30m', '6h', '7d', or ISO 8601."
        ) from None


def _open(db_path: str) -> LatencyXDB:
    try:
        return LatencyXDB(db_path)
    except FileNotFoundError:
        raise HTTPException(
            503, "Database not found — start your app first and make a few requests."
        ) from None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(db_path: str) -> FastAPI:
    app = FastAPI(title="LatencyX", docs_url=None, redoc_url=None)
    _html = _load_ui()

    @app.get("/", response_class=HTMLResponse)
    def root() -> str:
        return _html

    # ── /api/stats ──────────────────────────────────────────────────────────

    @app.get("/api/stats")
    def api_stats(since: str = "6h") -> dict[str, Any]:
        since_ts = _parse_since_http(since)
        with _open(db_path) as db:
            stats = db.get_global_stats(since_ts)
            endpoints = db.get_endpoints(since_ts)
            span_count = db.get_span_count()

        total = stats["total"]
        errors = stats["errors"]
        durations = sorted(stats["durations"])

        slowest: dict[str, Any] | None = None
        if endpoints:
            ep = max(endpoints, key=lambda e: e["p95"] or 0)
            slowest = {"name": ep["name"], "p95": ep["p95"] or 0}

        return {
            "total": total,
            "errors": errors,
            "error_rate": round(errors / total * 100, 2) if total > 0 else 0.0,
            "p50": percentile(durations, 50),
            "p95": percentile(durations, 95),
            "p99": percentile(durations, 99),
            "slowest": slowest,
            "span_count": span_count,
            "db_name": Path(db_path).name,
        }

    # ── /api/endpoints ───────────────────────────────────────────────────────

    @app.get("/api/endpoints")
    def api_endpoints(since: str = "6h", sort: str = "p95", limit: int = 25) -> list[Any]:
        since_ts = _parse_since_http(since)
        with _open(db_path) as db:
            endpoints = db.get_endpoints(since_ts)

        sort_fn: Any = {
            "p95": lambda e: e["p95"] or 0,
            "p50": lambda e: e["p50"] or 0,
            "count": lambda e: e["count"],
            "errors": lambda e: e["error_rate"],
        }.get(sort, lambda e: e["p95"] or 0)

        return sorted(endpoints, key=sort_fn, reverse=True)[:limit]

    # ── /api/traces ──────────────────────────────────────────────────────────

    @app.get("/api/traces")
    def api_traces(
        since: str = "6h",
        path: str | None = None,
        status: int | None = None,
        status_class: int | None = None,
        min_duration: float | None = None,
        limit: int = 50,
    ) -> list[Any]:
        since_ts = _parse_since_http(since)
        resolved_status = status
        status_range: tuple[int, int] | None = None
        if status_class is not None:
            status_range = (status_class * 100, status_class * 100 + 99)
        with _open(db_path) as db:
            rows = db.get_traces(
                since_ts,
                path=path,
                status_code=resolved_status,
                status_range=status_range,
                min_duration=min_duration,
                limit=limit,
            )
        return [dict(r) for r in rows]

    # ── /api/traces/{trace_id} ───────────────────────────────────────────────

    @app.get("/api/traces/{trace_id}")
    def api_trace_detail(trace_id: str) -> dict[str, Any]:
        with _open(db_path) as db:
            rows = db.get_trace(trace_id)

        if not rows:
            raise HTTPException(404, f"Trace not found: {trace_id}")

        flat = [dict(r) for r in rows]
        span_ids = {s["span_id"] for s in flat}
        roots = [s for s in flat if s.get("parent_span_id") not in span_ids]

        min_started = min(s["started_at"] for s in flat)
        total_dur = max(
            (s["started_at"] - min_started) * 1000 + (s["duration_ms"] or 0) for s in flat
        )

        def annotate(s: dict[str, Any]) -> dict[str, Any]:
            return {
                **s,
                "slow": (s["duration_ms"] or 0) > _SLOW_MS,
                "offset_ms": (s["started_at"] - min_started) * 1000,
                "children": [annotate(c) for c in flat if c.get("parent_span_id") == s["span_id"]],
            }

        return {
            "trace_id": trace_id,
            "span_count": len(flat),
            "total_duration_ms": max(total_dur, 1),
            "root_started_at": min_started,
            "spans": [annotate(r) for r in roots],
        }

    # ── /api/errors ──────────────────────────────────────────────────────────

    @app.get("/api/errors")
    def api_errors(since: str = "6h", path: str | None = None, limit: int = 25) -> list[Any]:
        since_ts = _parse_since_http(since)
        with _open(db_path) as db:
            rows = db.get_errors(since_ts, path=path, limit=limit)
        return [dict(r) for r in rows]

    # ── /api/sparklines ──────────────────────────────────────────────────────

    @app.get("/api/sparklines")
    def api_sparklines(since: str = "6h") -> dict[str, Any]:
        since_ts = _parse_since_http(since)
        with _open(db_path) as db:
            return db.get_sparklines(since_ts)

    # ── /api/volume ───────────────────────────────────────────────────────────

    @app.get("/api/volume")
    def api_volume(since: str = "6h") -> dict[str, Any]:
        since_ts = _parse_since_http(since)
        with _open(db_path) as db:
            return db.get_volume(since_ts)

    return app
