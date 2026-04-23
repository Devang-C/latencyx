from typing import Any, Optional

import flask
from flask import g, request

from ..core import timed


def instrument_flask(app: Any) -> None:
    @app.before_request
    def _latencyx_before() -> None:
        method = request.method
        ctx = timed(
            method,
            span_type="http.server",
            metadata={"method": method, "client": request.remote_addr},
        )
        span = ctx.__enter__()
        g._latencyx_ctx = ctx
        g._latencyx_span = span

    @app.after_request
    def _latencyx_after(response: flask.Response) -> flask.Response:
        span = getattr(g, "_latencyx_span", None)
        if span is not None:
            span.metadata["status_code"] = response.status_code
        return response

    @app.teardown_request
    def _latencyx_teardown(exc: Optional[BaseException]) -> None:
        ctx = getattr(g, "_latencyx_ctx", None)
        span = getattr(g, "_latencyx_span", None)
        if ctx is None:
            return
        rule = request.url_rule
        path = rule.rule if rule is not None else request.path
        if span is not None:
            span.name = f"{request.method} {path}"
            span.metadata["path"] = path
        # exc is non-None only when an exception escaped Flask's own error handling
        # (e.g. PROPAGATE_EXCEPTIONS=True in tests). Pass it through so timed()
        # records it on the span, then swallow the re-raise so teardown never crashes.
        try:
            ctx.__exit__(
                type(exc) if exc is not None else None,
                exc,
                exc.__traceback__ if exc is not None else None,
            )
        except Exception:
            pass
