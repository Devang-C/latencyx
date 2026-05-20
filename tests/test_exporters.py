import json
import logging
from pathlib import Path
from typing import Any, Optional

from latencyx.config import ExporterType, TimeUnit, config
from latencyx.core import Span


def make_span(
    name: str = "test_op",
    span_type: str = "generic",
    duration_ms: float = 50.0,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Span:
    span = Span(name, span_type, metadata or {})
    span.end = span.start + duration_ms / 1000
    span.duration_ms = duration_ms
    span.error = error
    return span


# ---------------------------------------------------------------------------
# ConsoleExporter
# ---------------------------------------------------------------------------


class TestConsoleExporter:
    def test_export_logs_info(self, caplog):
        from latencyx.exporters.console import ConsoleExporter

        exporter = ConsoleExporter()
        span = make_span()
        with caplog.at_level(logging.INFO, logger="latencyx"):
            exporter.export(span)
        assert "test_op" in caplog.text
        assert "50.00ms" in caplog.text

    def test_export_error_logs_at_error_level(self, caplog):
        from latencyx.exporters.console import ConsoleExporter

        exporter = ConsoleExporter()
        span = make_span(error="something failed")
        with caplog.at_level(logging.ERROR, logger="latencyx"):
            exporter.export(span)
        assert "ERROR=something failed" in caplog.text

    def test_export_includes_metadata(self, caplog):
        from latencyx.exporters.console import ConsoleExporter

        exporter = ConsoleExporter()
        span = make_span(metadata={"method": "GET", "status_code": 200})
        with caplog.at_level(logging.INFO, logger="latencyx"):
            exporter.export(span)
        assert "method=GET" in caplog.text
        assert "status=200" in caplog.text  # status_code is shortened to 'status'

    def test_format_duration_milliseconds(self):
        from latencyx.exporters.console import ConsoleExporter

        exporter = ConsoleExporter()
        assert exporter._format_duration(50.0) == "50.00ms"
        assert exporter._format_duration(150.0) == "150.0ms"
        assert exporter._format_duration(1500.0) == "1.50s"

    def test_format_duration_seconds_unit(self):
        from latencyx.exporters.console import ConsoleExporter

        config.time_unit = TimeUnit.SECONDS
        exporter = ConsoleExporter()
        result = exporter._format_duration(500.0)
        assert result == "0.500s"

    def test_priority_field_ordering(self, caplog):
        from latencyx.exporters.console import ConsoleExporter

        exporter = ConsoleExporter()
        span = make_span(metadata={"custom": "data", "status_code": 200, "method": "POST"})
        with caplog.at_level(logging.INFO, logger="latencyx"):
            exporter.export(span)
        # status and method should appear before custom
        log_line = caplog.text
        assert log_line.index("status=200") < log_line.index("custom=data")


# ---------------------------------------------------------------------------
# JsonFileExporter
# ---------------------------------------------------------------------------


class TestJsonFileExporter:
    def test_export_writes_valid_jsonl(self, tmp_path):
        from latencyx.exporters.json_file import JsonFileExporter

        config.json_file_path = str(tmp_path / "traces.jsonl")
        exporter = JsonFileExporter()
        exporter.export(make_span(name="op1", duration_ms=42.0))

        lines = Path(config.json_file_path).read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["span_name"] == "op1"
        assert record["duration_ms"] == 42.0
        assert record["status"] == "success"
        assert "timestamp" in record

    def test_export_error_span(self, tmp_path):
        from latencyx.exporters.json_file import JsonFileExporter

        config.json_file_path = str(tmp_path / "traces.jsonl")
        exporter = JsonFileExporter()
        exporter.export(make_span(error="db connection failed"))

        record = json.loads(Path(config.json_file_path).read_text())
        assert record["status"] == "error"
        assert record["error"] == "db connection failed"

    def test_export_flattens_metadata(self, tmp_path):
        from latencyx.exporters.json_file import JsonFileExporter

        config.json_file_path = str(tmp_path / "traces.jsonl")
        exporter = JsonFileExporter()
        exporter.export(make_span(metadata={"status_code": 201, "method": "POST"}))

        record = json.loads(Path(config.json_file_path).read_text())
        assert record["status_code"] == 201
        assert record["method"] == "POST"

    def test_export_appends_multiple_lines(self, tmp_path):
        from latencyx.exporters.json_file import JsonFileExporter

        config.json_file_path = str(tmp_path / "traces.jsonl")
        exporter = JsonFileExporter()
        exporter.export(make_span(name="op1"))
        exporter.export(make_span(name="op2"))
        exporter.export(make_span(name="op3"))

        lines = Path(config.json_file_path).read_text().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["span_name"] == "op1"
        assert json.loads(lines[2])["span_name"] == "op3"

    def test_timestamp_is_utc_aware(self, tmp_path):
        from latencyx.exporters.json_file import JsonFileExporter

        config.json_file_path = str(tmp_path / "traces.jsonl")
        exporter = JsonFileExporter()
        exporter.export(make_span())

        record = json.loads(Path(config.json_file_path).read_text())
        # UTC-aware timestamps end with +00:00
        assert "+00:00" in record["timestamp"]

    def test_export_silently_handles_io_error(self, tmp_path, monkeypatch):
        from latencyx.exporters import json_file as jf_module

        config.json_file_path = str(tmp_path / "traces.jsonl")
        exporter = jf_module.JsonFileExporter()

        def raise_oserror(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr("builtins.open", raise_oserror)
        exporter.export(make_span())  # should not raise


# ---------------------------------------------------------------------------
# SQLiteExporter
# ---------------------------------------------------------------------------


class TestSQLiteExporter:
    def test_export_writes_row(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span(name="db_op", duration_ms=25.0))

        conn = sqlite3.connect(config.sqlite_path)
        rows = conn.execute("SELECT span_name, duration_ms, status FROM spans").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0] == ("db_op", 25.0, "success")

    def test_export_error_span(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span(error="timeout"))

        conn = sqlite3.connect(config.sqlite_path)
        row = conn.execute("SELECT status, error FROM spans").fetchone()
        conn.close()

        assert row == ("error", "timeout")

    def test_export_known_metadata_fields_get_columns(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span(metadata={"method": "GET", "path": "/users", "status_code": 200}))

        conn = sqlite3.connect(config.sqlite_path)
        row = conn.execute("SELECT method, path, status_code FROM spans").fetchone()
        conn.close()

        assert row == ("GET", "/users", 200)

    def test_export_unknown_metadata_goes_to_extra_json(self, tmp_path):
        import json
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span(metadata={"custom_tag": "payments", "version": "v2"}))

        conn = sqlite3.connect(config.sqlite_path)
        row = conn.execute("SELECT extra_metadata FROM spans").fetchone()
        conn.close()

        extra = json.loads(row[0])
        assert extra["custom_tag"] == "payments"
        assert extra["version"] == "v2"

    def test_export_appends_multiple_rows(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span(name="op1"))
        exporter.export(make_span(name="op2"))
        exporter.export(make_span(name="op3"))

        conn = sqlite3.connect(config.sqlite_path)
        rows = conn.execute("SELECT span_name FROM spans ORDER BY id").fetchall()
        conn.close()

        assert [r[0] for r in rows] == ["op1", "op2", "op3"]

    def test_export_timestamp_is_utc(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span())

        conn = sqlite3.connect(config.sqlite_path)
        ts = conn.execute("SELECT timestamp FROM spans").fetchone()[0]
        conn.close()

        assert "+00:00" in ts

    def test_export_silently_handles_db_error(self, tmp_path):
        import sqlite3 as sqlite3_module
        from unittest.mock import MagicMock

        from latencyx.exporters import sqlite as sqlite_module

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = sqlite_module.SQLiteExporter()
        real_conn = exporter._conn

        # sqlite3.Connection.execute is a C slot and can't be monkeypatched,
        # so replace the whole connection with a mock that raises on execute.
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlite3_module.Error("disk full")
        exporter._conn = mock_conn

        exporter.export(make_span())  # must not raise

        # Restore real connection so the conftest fixture can close it cleanly
        exporter._conn = real_conn

    def test_creates_parent_directories(self, tmp_path):
        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "nested" / "dir" / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span())

        import sqlite3

        conn = sqlite3.connect(config.sqlite_path)
        count = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        conn.close()
        assert count == 1

    def test_export_stores_trace_and_span_ids(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span())

        conn = sqlite3.connect(config.sqlite_path)
        row = conn.execute("SELECT trace_id, span_id FROM spans").fetchone()
        conn.close()

        assert row[0] is not None and len(row[0]) == 32  # trace_id
        assert row[1] is not None and len(row[1]) == 32  # span_id

    def test_export_stores_parent_span_id(self, tmp_path):
        import sqlite3

        from latencyx.core import Span
        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()

        parent = Span("parent")
        parent.end = parent.start + 0.1
        parent.duration_ms = 100.0

        child = Span("child")
        child.parent = parent
        child.trace_id = parent.trace_id
        child.end = child.start + 0.05
        child.duration_ms = 50.0

        exporter.export(parent)
        exporter.export(child)

        conn = sqlite3.connect(config.sqlite_path)
        rows = conn.execute(
            "SELECT span_name, span_id, parent_span_id FROM spans ORDER BY id"
        ).fetchall()
        conn.close()

        parent_row, child_row = rows
        assert parent_row[2] is None  # root span has no parent
        assert child_row[2] == parent_row[1]  # child points to parent's span_id

    def test_export_stores_service_name(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        config.service_name = "payments-api"
        exporter = SQLiteExporter()
        exporter.export(make_span())

        conn = sqlite3.connect(config.sqlite_path)
        name = conn.execute("SELECT service_name FROM spans").fetchone()[0]
        conn.close()

        assert name == "payments-api"

    def test_export_stores_started_at_as_unix_epoch(self, tmp_path):
        import sqlite3
        import time

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        before = time.time()
        exporter.export(make_span())
        after = time.time()

        conn = sqlite3.connect(config.sqlite_path)
        started_at = conn.execute("SELECT started_at FROM spans").fetchone()[0]
        conn.close()

        assert before <= started_at <= after

    def test_export_stores_url(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        exporter = SQLiteExporter()
        exporter.export(make_span(metadata={"url": "https://api.github.com/users/github"}))

        conn = sqlite3.connect(config.sqlite_path)
        row = conn.execute("SELECT url, extra_metadata FROM spans").fetchone()
        conn.close()

        assert row[0] == "https://api.github.com/users/github"
        assert row[1] is None  # url must NOT also appear in extra_metadata

    def test_wal_mode_enabled(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        SQLiteExporter()

        conn = sqlite3.connect(config.sqlite_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()

        assert mode == "wal"

    def test_schema_version_recorded(self, tmp_path):
        import sqlite3

        from latencyx.exporters.sqlite import SCHEMA_VERSION, SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        SQLiteExporter()

        conn = sqlite3.connect(config.sqlite_path)
        version = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()

        assert version == SCHEMA_VERSION

    def test_retention_deletes_old_spans(self, tmp_path):
        import sqlite3
        import time

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        config.retention_days = 7

        exporter = SQLiteExporter()

        # Write a recent span
        recent = make_span(name="recent")
        exporter.export(recent)

        # Write an old span by backdating started_at
        old = make_span(name="old")
        old.started_at = time.time() - (8 * 86400)  # 8 days ago
        exporter.export(old)

        # Run cleanup directly (synchronously, bypassing the background thread)
        exporter._cleanup_old_spans()

        conn = sqlite3.connect(config.sqlite_path)
        names = [r[0] for r in conn.execute("SELECT span_name FROM spans").fetchall()]
        conn.close()
        exporter.close()

        assert "recent" in names
        assert "old" not in names

    def test_retention_keeps_all_spans_when_none(self, tmp_path):
        import sqlite3
        import time

        from latencyx.exporters.sqlite import SQLiteExporter

        config.sqlite_path = str(tmp_path / "traces.db")
        config.retention_days = None

        exporter = SQLiteExporter()

        old = make_span(name="old")
        old.started_at = time.time() - (365 * 86400)
        exporter.export(old)

        exporter._cleanup_old_spans()  # should be a no-op

        conn = sqlite3.connect(config.sqlite_path)
        count = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        conn.close()
        exporter.close()

        assert count == 1

    def test_retention_no_thread_spawned_when_none(self, tmp_path, monkeypatch):
        import threading

        from latencyx.exporters.sqlite import SQLiteExporter

        spawned = []
        original_thread = threading.Thread

        def tracking_thread(*args, **kwargs):
            spawned.append(kwargs.get("target"))
            return original_thread(*args, **kwargs)

        monkeypatch.setattr(threading, "Thread", tracking_thread)

        config.sqlite_path = str(tmp_path / "traces.db")
        config.retention_days = None
        exporter = SQLiteExporter()
        exporter.close()

        cleanup_threads = [
            t for t in spawned if t is not None and "cleanup" in getattr(t, "__name__", "")
        ]
        assert len(cleanup_threads) == 0


# ---------------------------------------------------------------------------
# init_exporters / export_span
# ---------------------------------------------------------------------------


class TestExporterRegistry:
    def test_init_exporters_console(self):
        import latencyx.exporters as exp_module
        from latencyx.exporters.console import ConsoleExporter

        config.exporters = [ExporterType.CONSOLE]
        exp_module.init_exporters()
        assert len(exp_module._exporters) == 1
        assert isinstance(exp_module._exporters[0], ConsoleExporter)

    def test_init_exporters_json_file(self, tmp_path):
        import latencyx.exporters as exp_module
        from latencyx.exporters.json_file import JsonFileExporter

        config.exporters = [ExporterType.JSON_FILE]
        config.json_file_path = str(tmp_path / "t.jsonl")
        exp_module.init_exporters()
        assert len(exp_module._exporters) == 1
        assert isinstance(exp_module._exporters[0], JsonFileExporter)

    def test_init_exporters_sqlite(self, tmp_path):
        import latencyx.exporters as exp_module
        from latencyx.exporters.sqlite import SQLiteExporter

        config.exporters = [ExporterType.SQLITE]
        config.sqlite_path = str(tmp_path / "t.db")
        exp_module.init_exporters()
        assert len(exp_module._exporters) == 1
        assert isinstance(exp_module._exporters[0], SQLiteExporter)

    def test_init_exporters_all_three(self, tmp_path):
        import latencyx.exporters as exp_module

        config.exporters = [ExporterType.CONSOLE, ExporterType.JSON_FILE, ExporterType.SQLITE]
        config.json_file_path = str(tmp_path / "t.jsonl")
        config.sqlite_path = str(tmp_path / "t.db")
        exp_module.init_exporters()
        assert len(exp_module._exporters) == 3

    def test_export_span_calls_all_exporters(self, tmp_path, caplog):
        from latencyx.exporters import export_span, init_exporters

        config.exporters = [ExporterType.CONSOLE, ExporterType.JSON_FILE]
        config.json_file_path = str(tmp_path / "t.jsonl")
        init_exporters()

        with caplog.at_level(logging.INFO, logger="latencyx"):
            export_span(make_span(name="multi_export"))

        assert "multi_export" in caplog.text
        assert Path(config.json_file_path).exists()

    def test_export_span_continues_after_exporter_failure(self, tmp_path, caplog):
        """A broken exporter must not prevent other exporters from running."""
        import latencyx.exporters as exp_module

        config.exporters = [ExporterType.JSON_FILE]
        config.json_file_path = str(tmp_path / "t.jsonl")
        exp_module.init_exporters()

        class BrokenExporter:
            def export(self, span: Any) -> None:
                raise RuntimeError("I am broken")

        exp_module._exporters.insert(0, BrokenExporter())

        with caplog.at_level(logging.WARNING, logger="latencyx"):
            exp_module.export_span(make_span(name="resilience_test"))

        assert "BrokenExporter" in caplog.text
        lines = Path(config.json_file_path).read_text().splitlines()
        assert len(lines) == 1
