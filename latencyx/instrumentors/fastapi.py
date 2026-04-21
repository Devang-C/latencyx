from collections.abc import Awaitable
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..core import timed


class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method

        metadata: dict[str, Any] = {
            "method": method,
            "client": request.client.host if request.client else None,
        }

        with timed(method, span_type="http.server", metadata=metadata) as span:
            response = await call_next(request)

            # Route template is only available after call_next resolves routing
            route = request.scope.get("route")
            path = route.path if route else request.url.path
            name = f"{method} {path}"

            if span:
                span.name = name
                span.metadata["path"] = path
                span.metadata["status_code"] = response.status_code

        return response


def instrument_fastapi(app: Any) -> None:
    app.add_middleware(LatencyMiddleware)
