import random
import threading
import time
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Optional

from .config import ExporterType, TimeUnit, config


class _LocalState(threading.local):
    current_span: Optional["Span"] = None


_local = _LocalState()


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
        self.end: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None
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

    parent: Optional[Span] = _local.current_span
    span.parent = parent
    _local.current_span = span

    try:
        yield span
    except Exception as e:
        span.finish(error=e)
        raise
    finally:
        if span.end is None:
            span.finish()
        _local.current_span = parent


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

    if app is not None and config.instrument_fastapi:
        from .instrumentors.fastapi import instrument_fastapi

        instrument_fastapi(app)

    if config.instrument_http_client:
        try:
            from .instrumentors.http_client import instrument_http_client

            instrument_http_client()
        except (ImportError, AttributeError):
            pass
