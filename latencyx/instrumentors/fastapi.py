from starlette.middleware.base import BaseHTTPMiddleware
from ..core import timed

class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Get route path template
        route = request.scope.get("route")
        if route:
            path = route.path
        else:
            path = request.url.path
        
        method = request.method
        name = f"{method} {path}"
        
        metadata = {
            "method": method,
            "path": path,
            "client": request.client.host if request.client else None
        }
        
        with timed(name, span_type="http.server", metadata=metadata) as span:
            response = await call_next(request)
            if span:
                span.metadata["status_code"] = response.status_code
        
        return response

def instrument_fastapi(app):
    """Add instrumentation middleware to FastAPI app"""
    app.add_middleware(LatencyMiddleware)