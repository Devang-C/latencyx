import pytest

from latencyx.config import ExporterType, LatencyXConfig, TimeUnit


def test_default_values():
    c = LatencyXConfig()
    assert c.enabled is True
    assert c.time_unit == TimeUnit.MILLISECONDS
    assert c.exporters == [ExporterType.CONSOLE]
    assert c.json_file_path == "latencyx_traces.jsonl"
    assert c.instrument_fastapi is True
    assert c.instrument_http_client is True
    assert c.sample_rate == 1.0
    assert c.min_duration_ms == 0.0
    assert c.include_traceback is False


def test_exporter_type_values():
    assert ExporterType.CONSOLE.value == "console"
    assert ExporterType.JSON_FILE.value == "json_file"


def test_time_unit_values():
    assert TimeUnit.MILLISECONDS.value == "ms"
    assert TimeUnit.SECONDS.value == "s"


def test_exporter_type_from_string():
    assert ExporterType("console") == ExporterType.CONSOLE
    assert ExporterType("json_file") == ExporterType.JSON_FILE


def test_time_unit_from_string():
    assert TimeUnit("ms") == TimeUnit.MILLISECONDS
    assert TimeUnit("s") == TimeUnit.SECONDS


def test_invalid_exporter_type_raises():
    with pytest.raises(ValueError):
        ExporterType("prometheus")


def test_invalid_time_unit_raises():
    with pytest.raises(ValueError):
        TimeUnit("minutes")
