import random
import time
import traceback
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

from .config import ExporterType, TimeUnit, config

# Tracks the active span for the current coroutine (async) or thread (sync).
# ContextVar is isolated per-coroutine in asyncio and per-thread in sync code,
# making it correct for both — unlike threading.local which breaks under async.
_current_span_var: ContextVar[Optional["Span"]] = ContextVar("current_span", default=None)


class Span:
    def __init__(
        self,
        name: str,
        span_type: str = "generic",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.span_type = span_type
        self.metadata: dict[str, Any] = metadata or {}
        self.start = time.perf_counter()
        self.started_at: float = time.time()  # Unix epoch — stored in SQLite for range queries
        self.end: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None
        self.span_id: str = uuid.uuid4().hex  # unique per span
        self.trace_id: str = uuid.uuid4().hex  # overwritten by timed() when there's a parent
        self.parent: Optional[Span] = None

    def finish(self, error: Optional[Exception] = None) -> None:
        if not config.enabled:
            return

        self.end = time.perf_counter()
        self.duration_ms = (self.end - self.start) * 1000

        if self.duration_ms < config.min_duration_ms:
            return

        if error:
            self.error = str(error)
            if config.include_traceback:
                self.traceback = traceback.format_exc()

        from .exporters import export_span

        export_span(self)


@contextmanager
def timed(
    name: str,
    span_type: str = "generic",
    metadata: Optional[dict[str, Any]] = None,
) -> Generator[Optional[Span], None, None]:
    if not config.enabled or random.random() >= config.sample_rate:
        yield None
        return

    span = Span(name, span_type, metadata)

    parent: Optional[Span] = _current_span_var.get()
    span.parent = parent
    # All spans in the same request share a trace_id — inherit from parent or start a new trace
    if parent:
        span.trace_id = parent.trace_id
    token = _current_span_var.set(span)

    try:
        yield span
    except Exception as e:
        span.finish(error=e)
        raise
    finally:
        if span.end is None:
            span.finish()
        _current_span_var.reset(token)


def _auto_instrument(app: Any) -> None:
    """Detect whether app is FastAPI or Flask and wire the appropriate instrumentor."""
    module = type(app).__module__ or ""
    if "fastapi" in module:
        if config.instrument_fastapi:
            from .instrumentors.fastapi import instrument_fastapi

            instrument_fastapi(app)
    elif "flask" in module:
        if config.instrument_flask:
            from .instrumentors.flask import instrument_flask

            instrument_flask(app)


def init(app: Any = None, **kwargs: Any) -> None:
    for key, value in kwargs.items():
        if not hasattr(config, key):
            continue

        if key == "exporters" and value:
            converted = []
            for exp in value:
                converted.append(ExporterType(exp) if isinstance(exp, str) else exp)
            value = converted
        elif key == "time_unit" and isinstance(value, str):
            value = TimeUnit(value)
        elif key == "sample_rate":
            if not (0.0 <= value <= 1.0):
                raise ValueError("sample_rate must be between 0.0 and 1.0")

        setattr(config, key, value)

    # Fast-path: if disabled, skip all instrumentation entirely.
    # No middleware is added, no monkey-patching happens, and timed() becomes
    # a no-op — so there is truly zero overhead on the hot path.
    if not config.enabled:
        return

    from .exporters import init_exporters

    init_exporters()

    if app is not None:
        _auto_instrument(app)

    if config.instrument_http_client:
        try:
            from .instrumentors.http_client import instrument_http_client

            instrument_http_client()
        except (ImportError, AttributeError):
            pass
