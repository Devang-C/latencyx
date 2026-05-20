from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TimeUnit(str, Enum):
    MILLISECONDS = "ms"
    SECONDS = "s"


class ExporterType(str, Enum):
    CONSOLE = "console"
    JSON_FILE = "json_file"
    SQLITE = "sqlite"


@dataclass
class LatencyXConfig:
    enabled: bool = True
    time_unit: TimeUnit = TimeUnit.MILLISECONDS
    exporters: list[ExporterType] = field(default_factory=lambda: [ExporterType.SQLITE])
    json_file_path: str = "latencyx_traces.jsonl"
    # SQLite is the default local storage — queryable by the CLI commands
    sqlite_path: str = "latencyx_traces.db"
    service_name: str = "default"
    instrument_fastapi: bool = True
    instrument_flask: bool = True
    instrument_http_client: bool = True  # controls httpx instrumentation
    instrument_requests_client: bool = True  # controls requests instrumentation
    instrument_sqlalchemy: bool = True
    sqlalchemy_capture_params: bool = False
    sample_rate: float = 1.0
    min_duration_ms: float = 0.0
    include_traceback: bool = False
    # Spans older than this many days are deleted at startup. None = keep forever.
    retention_days: Optional[int] = None


# Global config instance
config = LatencyXConfig()
