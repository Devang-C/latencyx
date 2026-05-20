"""Tests for the requests library instrumentor."""

from unittest.mock import MagicMock, patch

import pytest

from latencyx.config import ExporterType, config


@pytest.fixture
def sqlite_exporter(tmp_path):
    config.exporters = [ExporterType.SQLITE]
    config.sqlite_path = str(tmp_path / "traces.db")

    import latencyx.exporters as exp_module

    exp_module.init_exporters()
    yield
    for exp in exp_module._exporters:
        if hasattr(exp, "close"):
            exp.close()
    exp_module._exporters.clear()


def _make_mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


class TestRequestsClientInstrumentor:
    def test_patches_session_send(self):
        import requests

        from latencyx.instrumentors.requests_client import instrument_requests_client

        original = requests.Session.send
        instrument_requests_client()

        assert requests.Session.send is not original

    def test_idempotent_patching(self):
        """Calling instrument_requests_client twice must not double-wrap."""
        import requests

        from latencyx.instrumentors.requests_client import instrument_requests_client

        instrument_requests_client()
        patched_once = requests.Session.send

        instrument_requests_client()

        assert requests.Session.send is patched_once

    def test_span_created_on_send(self, sqlite_exporter, tmp_path):
        import sqlite3

        from latencyx.instrumentors.requests_client import (
            instrument_requests_client,
        )

        instrument_requests_client()

        mock_response = _make_mock_response(200)
        prepared = MagicMock()
        prepared.method = "GET"
        prepared.url = "https://api.example.com/users"

        with patch(
            "latencyx.instrumentors.requests_client._original_send",
            return_value=mock_response,
        ):
            import requests

            session = requests.Session()
            session.send(prepared)

        conn = sqlite3.connect(config.sqlite_path)
        rows = conn.execute("SELECT span_name, span_type, status_code FROM spans").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][1] == "http.client"
        assert rows[0][2] == 200

    def test_span_name_includes_method_and_path(self, sqlite_exporter):
        import sqlite3

        from latencyx.instrumentors.requests_client import instrument_requests_client

        instrument_requests_client()

        mock_response = _make_mock_response(201)
        prepared = MagicMock()
        prepared.method = "POST"
        prepared.url = "https://api.example.com/orders"

        with patch(
            "latencyx.instrumentors.requests_client._original_send",
            return_value=mock_response,
        ):
            import requests

            session = requests.Session()
            session.send(prepared)

        conn = sqlite3.connect(config.sqlite_path)
        name = conn.execute("SELECT span_name FROM spans").fetchone()[0]
        conn.close()

        assert "POST" in name
        assert "/orders" in name

    def test_original_send_still_called(self):
        """The wrapper must call through to the original send."""
        from latencyx.instrumentors.requests_client import instrument_requests_client

        instrument_requests_client()

        mock_response = _make_mock_response(200)
        prepared = MagicMock()
        prepared.method = "GET"
        prepared.url = "https://api.example.com/ping"

        with patch(
            "latencyx.instrumentors.requests_client._original_send",
            return_value=mock_response,
        ) as mock_send:
            import requests

            session = requests.Session()
            result = session.send(prepared)

        mock_send.assert_called_once()
        assert result is mock_response

    def test_no_patch_when_requests_not_installed(self, monkeypatch):
        import latencyx.instrumentors.requests_client as rc_module

        monkeypatch.setattr(rc_module, "_requests_lib", None)
        monkeypatch.setattr(rc_module, "_original_send", None)

        rc_module.instrument_requests_client()

        assert rc_module._original_send is None

    def test_disabled_config_skips_instrumentation(self):
        """instrument_requests_client=False in config prevents patching in init()."""
        import requests

        original = requests.Session.send
        config.instrument_requests_client = False

        from latencyx.core import init

        init()

        assert requests.Session.send is original

    def test_error_propagates_from_traced_send(self):
        """Exceptions raised by the underlying send must propagate to the caller."""
        from latencyx.instrumentors.requests_client import instrument_requests_client

        instrument_requests_client()

        prepared = MagicMock()
        prepared.method = "GET"
        prepared.url = "https://api.example.com/boom"

        with patch(
            "latencyx.instrumentors.requests_client._original_send",
            side_effect=ConnectionError("network unreachable"),
        ):
            import requests

            session = requests.Session()
            with pytest.raises(ConnectionError, match="network unreachable"):
                session.send(prepared)
