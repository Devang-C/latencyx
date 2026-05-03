import threading
from typing import Any, Callable, Optional
from urllib.parse import urlparse

try:
    import requests as _requests_lib  # type: ignore[import-untyped]
except ImportError:
    _requests_lib = None  # type: ignore[assignment]

from ..core import timed

# Patching Session.send (not Session.request) because all top-level helpers
# (requests.get, requests.post, etc.) ultimately funnel through Session.send,
# making it the single correct interception point.
_original_send: Optional[Callable[..., Any]] = None
_instrumentation_lock = threading.Lock()


def instrument_requests_client() -> None:
    global _original_send

    if _requests_lib is None:
        return

    with _instrumentation_lock:
        if _original_send is not None:
            return  # already patched — idempotent

        _original_send = _requests_lib.Session.send

        def traced_send(self: Any, request: Any, **kwargs: Any) -> Any:
            parsed = urlparse(request.url)
            name = f"{request.method.upper()} {parsed.netloc}{parsed.path}"
            metadata = {
                "method": request.method.upper(),
                "url": request.url,
                "host": parsed.netloc,
            }

            with timed(name, span_type="http.client", metadata=metadata) as span:
                response = _original_send(self, request, **kwargs)  # type: ignore[misc]
                if span:
                    span.metadata["status_code"] = response.status_code
                return response

        _requests_lib.Session.send = traced_send  # type: ignore[method-assign]
