import logging
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import latencyx
from latencyx.config import config


def make_app_with_latencyx(**init_kwargs) -> tuple:
    app = FastAPI()

    @app.get("/hello")
    async def hello():
        return {"message": "hello"}

    @app.post("/items")
    async def create_item():
        return {"id": 1}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("intentional error")

    latencyx.init(app=app, exporters=["console"], **init_kwargs)
    return app, TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------


def test_middleware_traces_get_request(caplog):
    app, client = make_app_with_latencyx()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        resp = client.get("/hello")

    assert resp.status_code == 200
    assert "GET /hello" in caplog.text
    assert "http.server" in caplog.text


def test_middleware_traces_post_request(caplog):
    app, client = make_app_with_latencyx()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        resp = client.post("/items")

    assert resp.status_code == 200
    assert "POST /items" in caplog.text


def test_middleware_records_status_code(caplog):
    app, client = make_app_with_latencyx()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        client.get("/hello")

    assert "status=200" in caplog.text


def test_middleware_records_404(caplog):
    app, client = make_app_with_latencyx()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        resp = client.get("/nonexistent")

    assert resp.status_code == 404
    # 404 is still traced (it's a valid response)
    assert "status=404" in caplog.text


def test_middleware_export_span_called():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], instrument_http_client=False)
        client = TestClient(app)
        client.get("/ping")

        assert mock_export.called
        server_spans = [
            call.args[0]
            for call in mock_export.call_args_list
            if call.args[0].span_type == "http.server"
        ]
        assert len(server_spans) == 1
        span = server_spans[0]
        assert span.metadata.get("method") == "GET"
        assert span.metadata.get("status_code") == 200


def test_middleware_span_name_uses_route_template():
    """Should use /items/{item_id} not /items/42."""
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def get_item(item_id: int):
        return {"id": item_id}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], instrument_http_client=False)
        client = TestClient(app)
        client.get("/items/42")

        server_spans = [
            call.args[0]
            for call in mock_export.call_args_list
            if call.args[0].span_type == "http.server"
        ]
        assert len(server_spans) == 1
        assert server_spans[0].name == "GET /items/{item_id}"


def test_middleware_respects_min_duration_filter():
    app = FastAPI()

    @app.get("/fast")
    async def fast():
        return {}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], min_duration_ms=9999.0)
        client = TestClient(app)
        client.get("/fast")

        assert not mock_export.called


def test_middleware_respects_disabled():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {}

    latencyx.init(app=app, exporters=["console"])

    with patch("latencyx.exporters.export_span") as mock_export:
        config.enabled = False
        client = TestClient(app)
        client.get("/ping")

        assert not mock_export.called


def test_init_enabled_false_skips_middleware():
    """init(enabled=False) must not add middleware — zero overhead on every request."""
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], enabled=False)
        client = TestClient(app)
        client.get("/ping")

        # Middleware was never added, so export_span is never reached
        assert not mock_export.called
        # Confirm the flag is actually False (not silently overridden to True)
        assert config.enabled is False
