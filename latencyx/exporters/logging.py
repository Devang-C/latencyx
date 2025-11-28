# latencyx/exporters/logging.py
import json
import logging
from ..core import config  # ← import the config object

logger = logging.getLogger("latencyx")

def log_span(span, duration_ms: float):
    # if not config.enabled:  # ← access through config object
    #     return

    record = {
        "name": span.name,
        "duration_ms": round(duration_ms, 3),
    }
    logger.info("%s", json.dumps(record))