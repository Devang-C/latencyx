from dataclasses import dataclass, field
from enum import Enum


class TimeUnit(str, Enum):
    MILLISECONDS = "ms"
    SECONDS = "s"


class ExporterType(str, Enum):
    CONSOLE = "console"
    JSON_FILE = "json_file"


@dataclass
class LatencyXConfig:
    enabled: bool = True
    time_unit: TimeUnit = TimeUnit.MILLISECONDS
    exporters: list[ExporterType] = field(default_factory=lambda: [ExporterType.CONSOLE])
    json_file_path: str = "latencyx_traces.jsonl"
    instrument_fastapi: bool = True
    instrument_http_client: bool = True
    sample_rate: float = 1.0
    min_duration_ms: float = 0.0
    include_traceback: bool = False


# Global config instance
config = LatencyXConfig()
