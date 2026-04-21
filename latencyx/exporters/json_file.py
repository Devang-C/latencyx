import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import config


class JsonFileExporter:
    def __init__(self) -> None:
        self.file_path = Path(config.json_file_path)
        self.file_path.touch(exist_ok=True)

    def export(self, span: Any) -> None:
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "span_name": span.name,
            "span_type": span.span_type,
            "duration_ms": round(span.duration_ms, 3),
            "status": "error" if span.error else "success",
        }

        if span.metadata:
            for key, value in span.metadata.items():
                if key not in record:
                    record[key] = value

        if span.error:
            record["error"] = span.error
            if span.traceback:
                record["traceback"] = span.traceback

        try:
            with open(self.file_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass
