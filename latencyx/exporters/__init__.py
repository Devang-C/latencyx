import logging
from typing import Any

from ..config import ExporterType, config

logger = logging.getLogger("latencyx")

_exporters: list[Any] = []


def init_exporters() -> None:
    global _exporters
    _exporters = []

    for exporter_type in config.exporters:
        if exporter_type == ExporterType.CONSOLE:
            from .console import ConsoleExporter

            _exporters.append(ConsoleExporter())
        elif exporter_type == ExporterType.JSON_FILE:
            from .json_file import JsonFileExporter

            _exporters.append(JsonFileExporter())
        elif exporter_type == ExporterType.SQLITE:
            from .sqlite import SQLiteExporter

            _exporters.append(SQLiteExporter())


def export_span(span: Any) -> None:
    for exporter in _exporters:
        try:
            exporter.export(span)
        except Exception as e:
            logger.warning("Error exporting to %s: %s", exporter.__class__.__name__, e)
