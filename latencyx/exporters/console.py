import logging
from typing import Any

from ..config import TimeUnit, config

logger = logging.getLogger("latencyx")


class ConsoleExporter:
    def export(self, span: Any) -> None:
        duration_str = self._format_duration(span.duration_ms)

        parts = [f"[{span.span_type}]", span.name, f"duration={duration_str}"]

        if span.metadata:
            priority_fields = ["status_code", "method", "client", "host"]

            for field in priority_fields:
                if field in span.metadata:
                    display_name = "status" if field == "status_code" else field
                    parts.append(f"{display_name}={span.metadata[field]}")

            for key, value in span.metadata.items():
                if key not in priority_fields:
                    parts.append(f"{key}={value}")

        if span.error:
            parts.append(f"ERROR={span.error}")

        message = " ".join(parts)

        if span.error:
            logger.error(message)
        else:
            logger.info(message)

    def _format_duration(self, duration_ms: float) -> str:
        if config.time_unit == TimeUnit.SECONDS:
            return f"{duration_ms / 1000:.3f}s"

        if duration_ms < 100:
            return f"{duration_ms:.2f}ms"
        elif duration_ms < 1000:
            return f"{duration_ms:.1f}ms"
        else:
            return f"{duration_ms / 1000:.2f}s"
