from typing import List
from ..config import config, ExporterType

_exporters = []

def init_exporters():
    """Initialize all configured exporters"""
    global _exporters
    _exporters = []
    
    for exporter_type in config.exporters:
        if exporter_type == ExporterType.CONSOLE:
            from .console import ConsoleExporter
            _exporters.append(ConsoleExporter())
        
        elif exporter_type == ExporterType.JSON_FILE:
            from .json_file import JsonFileExporter
            _exporters.append(JsonFileExporter())
        

def export_span(span):
    """Export span to all configured exporters"""
    for exporter in _exporters:
        try:
            exporter.export(span)
        except Exception as e:
            print(f"Error exporting to {exporter.__class__.__name__}: {e}")