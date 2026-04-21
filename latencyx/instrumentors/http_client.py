import threading
from typing import Any, Callable, Optional
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from ..core import timed

_original_httpx_request: Optional[Callable[..., Any]] = None
_instrumentation_lock = threading.Lock()


def instrument_http_client() -> None:
    global _original_httpx_request

    if httpx is None:
        return

    with _instrumentation_lock:
        if _original_httpx_request is not None:
            return

        _original_httpx_request = httpx.Client.request

    def traced_request(self: Any, method: str, url: Any, **kwargs: Any) -> Any:
        parsed = urlparse(str(url))
        name = f"{method.upper()} {parsed.netloc}{parsed.path}"
        metadata = {"method": method.upper(), "url": str(url), "host": parsed.netloc}

        with timed(name, span_type="http.client", metadata=metadata) as span:
            response = _original_httpx_request(self, method, url, **kwargs)  # type: ignore[misc]
            if span:
                span.metadata["status_code"] = response.status_code
            return response

    httpx.Client.request = traced_request  # type: ignore[method-assign]

    _original_async_request = httpx.AsyncClient.request

    async def traced_async_request(self: Any, method: str, url: Any, **kwargs: Any) -> Any:
        parsed = urlparse(str(url))
        name = f"{method.upper()} {parsed.netloc}{parsed.path}"
        metadata = {"method": method.upper(), "url": str(url), "host": parsed.netloc}

        with timed(name, span_type="http.client", metadata=metadata) as span:
            response = await _original_async_request(self, method, url, **kwargs)
            if span:
                span.metadata["status_code"] = response.status_code
            return response

    httpx.AsyncClient.request = traced_async_request  # type: ignore[method-assign]
