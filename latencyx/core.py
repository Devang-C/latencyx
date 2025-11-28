
from contextlib import contextmanager
import time
import threading
from typing import Optional, Dict, Any
from .config import config
import traceback
import random

# Thread-local storage for current span
_local = threading.local()

class Span:
    def __init__(self, name: str, span_type: str = "generic", metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.span_type = span_type  # e.g., "http", "db", "cache"
        self.metadata = metadata or {}
        self.start = time.perf_counter()
        self.end: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None
    
    def finish(self, error: Optional[Exception] = None):
        if not config.enabled:
            return
            
        self.end = time.perf_counter()
        self.duration_ms = (self.end - self.start) * 1000
        
        # Check if we should record this span
        if self.duration_ms < config.min_duration_ms:
            return
        
        # Record error if present
        if error:
            self.error = str(error)
            if config.include_traceback:
                self.traceback = traceback.format_exc()
        
        # Export to all configured exporters
        from .exporters import export_span
        export_span(self)

@contextmanager
def timed(name: str, span_type: str = "generic", metadata: Optional[Dict[str, Any]] = None):
    """Context manager for timing operations"""
    # Check if we should sample this span
    if not config.enabled or random.random() >= config.sample_rate:
        # Not sampled - yield a no-op object
        yield None
        return

    span = Span(name, span_type, metadata)
    
    # Store parent span if exists
    parent = getattr(_local, "current_span", None)
    span.parent = parent
    _local.current_span = span
    
    try:
        yield span
    except Exception as e:
        span.finish(error=e)
        raise
    finally:
        if span.end is None:  # If no error occurred
            span.finish()
        _local.current_span = parent


def init(app=None, **kwargs):
    """
    Initialize LatencyX instrumentation
    
    Args:
        app: FastAPI/Flask app instance (optional)
        **kwargs: Configuration options (see LatencyXConfig)
    
    Example:
        latencyx.init(
            app=app,
            exporters=["console", "json_file"],
            time_unit="ms",
            instrument_http_client=True
        )
    """
    from .config import ExporterType, TimeUnit
    
    # Update config with user preferences
    for key, value in kwargs.items():
        if hasattr(config, key):
            # Convert string exporters to ExporterType enum
            if key == "exporters" and value:
                converted = []
                for exp in value:
                    if isinstance(exp, str):
                        converted.append(ExporterType(exp))
                    else:
                        converted.append(exp)
                value = converted
            
            # Convert string time_unit to TimeUnit enum
            elif key == "time_unit" and isinstance(value, str):
                value = TimeUnit(value)
            
            # Validate sample_rate
            elif key == "sample_rate":
                if not (0.0 <= value <= 1.0):
                    raise ValueError("sample_rate must be between 0.0 and 1.0")

            setattr(config, key, value)
    
    config.enabled = True
    
    # Initialize exporters
    from .exporters import init_exporters
    init_exporters()
    
    # Auto-instrument FastAPI if app provided
    if app is not None and config.instrument_fastapi:
        from .instrumentors.fastapi import instrument_fastapi
        instrument_fastapi(app)
    
    # Auto-instrument HTTP client
    if config.instrument_http_client:
        try:
            from .instrumentors.http_client import instrument_http_client
            instrument_http_client()
        except (ImportError, AttributeError):
            pass  # httpx not installed or not available
    
    # Auto-instrument psycopg2 - Archived for v1
    # if config.instrument_psycopg2:
    #     try:
    #         from .instrumentors.psycopg2 import instrument_psycopg2
    #         instrument_psycopg2()
    #     except ImportError:
    #         pass  # psycopg2 not installed
    
    exporter_names = [e.value if hasattr(e, 'value') else str(e) for e in config.exporters]
    # print(f"LatencyX initialized with exporters: {exporter_names}")