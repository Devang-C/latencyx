import json
from datetime import datetime
from pathlib import Path
from ..config import config

class JsonFileExporter:
    """Export spans to JSONL file"""
    
    def __init__(self):
        self.file_path = Path(config.json_file_path)
        # Create file if doesn't exist
        self.file_path.touch(exist_ok=True)
    
    def export(self, span):
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "span_name": span.name,
            "span_type": span.span_type,
            "duration_ms": round(span.duration_ms, 3),
            "status": "error" if span.error else "success",
        }
        
        # Flatten important metadata to top level
        if span.metadata:
            for key, value in span.metadata.items():
                # Avoid conflicts with existing keys
                if key not in record:
                    record[key] = value
        
        if span.error:
            record["error"] = span.error
            if span.traceback:
                record["traceback"] = span.traceback
        
        try:
            with open(self.file_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except (IOError, OSError):
            # Silently fail - exporter error handling will catch this
            pass
