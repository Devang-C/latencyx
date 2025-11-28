try:
    import httpx
except ImportError:
    httpx = None

import threading
from urllib.parse import urlparse
from ..core import timed

# Store original methods
_original_httpx_request = None
_instrumentation_lock = threading.Lock()

def instrument_http_client():
    """Instrument httpx for HTTP client calls"""
    global _original_httpx_request
    
    if httpx is None:
        return  # httpx not installed
    
    with _instrumentation_lock:
        if _original_httpx_request is not None:
            return  # Already instrumented
        
        _original_httpx_request = httpx.Client.request
    
    def traced_request(self, method, url, **kwargs):
        parsed = urlparse(str(url))
        name = f"{method.upper()} {parsed.netloc}{parsed.path}"
        
        metadata = {
            "method": method.upper(),
            "url": str(url),
            "host": parsed.netloc
        }
        
        with timed(name, span_type="http.client", metadata=metadata) as span:
            response = _original_httpx_request(self, method, url, **kwargs)
            if span:
                span.metadata["status_code"] = response.status_code
            return response
    
    httpx.Client.request = traced_request
    
    # Also instrument async client
    _original_async_request = httpx.AsyncClient.request
    
    async def traced_async_request(self, method, url, **kwargs):
        parsed = urlparse(str(url))
        name = f"{method.upper()} {parsed.netloc}{parsed.path}"
        
        metadata = {
            "method": method.upper(),
            "url": str(url),
            "host": parsed.netloc
        }
        
        with timed(name, span_type="http.client", metadata=metadata) as span:
            response = await _original_async_request(self, method, url, **kwargs)
            if span:
                span.metadata["status_code"] = response.status_code
            return response
    
    httpx.AsyncClient.request = traced_async_request