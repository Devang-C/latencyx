from dataclasses import dataclass, field
from typing import List, Literal
from enum import Enum

class TimeUnit(str,Enum):
    MILLISECONDS = "ms"
    SECONDS = "s"


class ExporterType(str, Enum):
    CONSOLE = "console"
    JSON_FILE = "json_file"

@dataclass
class LatencyXConfig:
    """Configuration for LatencyX instrumentation"""
    
    # Core settings
    enabled: bool = True
    time_unit: TimeUnit = TimeUnit.MILLISECONDS
    
    # Exporters
    exporters: List[ExporterType] = field(default_factory=lambda: [ExporterType.CONSOLE])
    json_file_path: str = "latencyx_traces.jsonl"
    
    # Instrumentation flags
    instrument_fastapi: bool = True
    instrument_http_client: bool = True
    # instrument_psycopg2: bool = True  # Archived for v1
    # instrument_redis: bool = False  # Optional, can add later
    
    # Advanced options
    sample_rate: float = 1.0  # 1.0 = 100% sampling
    min_duration_ms: float = 0.0  # Only log spans above this duration
    include_traceback: bool = False  # Include stack traces for slow requests

# Global config instance
config = LatencyXConfig()