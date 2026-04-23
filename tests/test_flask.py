import logging
from unittest.mock import patch

from flask import Flask

import latencyx
from latencyx.config import config


def make_flask_app(**init_kwargs) -> tuple:
    app = Flask(__name__)
    # Prevent Flask from propagating exceptions so 500s become proper responses,
    # matching test_fastapi.py's raise_server_exceptions=False behaviour.
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/hello")
    def hello():
        return {"message": "hello"}

    @app.post("/items")
    def create_item():
        return {"id": 1}, 201

    @app.get("/error")
    def error_endpoint():
        raise ValueError("intentional error")

    @app.get("/items/<int:item_id>")
    def get_item(item_id: int):
        return {"id": item_id}

    latencyx.init(app=app, exporters=["console"], **init_kwargs)
    return app, app.test_client()


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------


def test_flask_traces_get_request(caplog):
    _, client = make_flask_app()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        resp = client.get("/hello")

    assert resp.status_code == 200
    assert "GET /hello" in caplog.text
    assert "http.server" in caplog.text


def test_flask_traces_post_request(caplog):
    _, client = make_flask_app()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        resp = client.post("/items")

    assert resp.status_code == 201
    assert "POST /items" in caplog.text


def test_flask_records_status_code(caplog):
    _, client = make_flask_app()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        client.get("/hello")

    assert "status=200" in caplog.text


def test_flask_records_404(caplog):
    _, client = make_flask_app()

    with caplog.at_level(logging.INFO, logger="latencyx"):
        resp = client.get("/nonexistent")

    assert resp.status_code == 404
    assert "status=404" in caplog.text


def test_flask_export_span_called():
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/ping")
    def ping():
        return {"pong": True}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], instrument_http_client=False)
        client = app.test_client()
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


def test_flask_span_name_uses_route_template():
    """Should record /items/<int:item_id>, not /items/42."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/items/<int:item_id>")
    def get_item(item_id: int):
        return {"id": item_id}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], instrument_http_client=False)
        client = app.test_client()
        client.get("/items/42")

        server_spans = [
            call.args[0]
            for call in mock_export.call_args_list
            if call.args[0].span_type == "http.server"
        ]
        assert len(server_spans) == 1
        assert server_spans[0].name == "GET /items/<int:item_id>"


def test_flask_records_error_status_code():
    """500 responses are traced with status_code=500."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/boom")
    def boom():
        raise RuntimeError("explode")

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], instrument_http_client=False)
        client = app.test_client()
        resp = client.get("/boom")

        assert resp.status_code == 500
        server_spans = [
            call.args[0]
            for call in mock_export.call_args_list
            if call.args[0].span_type == "http.server"
        ]
        assert len(server_spans) == 1
        assert server_spans[0].metadata.get("status_code") == 500


def test_flask_respects_min_duration_filter():
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/fast")
    def fast():
        return {}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], min_duration_ms=9999.0)
        client = app.test_client()
        client.get("/fast")

        assert not mock_export.called


def test_flask_respects_disabled():
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/ping")
    def ping():
        return {}

    latencyx.init(app=app, exporters=["console"])

    with patch("latencyx.exporters.export_span") as mock_export:
        config.enabled = False
        client = app.test_client()
        client.get("/ping")

        assert not mock_export.called


def test_init_enabled_false_skips_flask_hooks():
    """init(enabled=False) must not register any hooks — zero overhead per request."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/ping")
    def ping():
        return {}

    with patch("latencyx.exporters.export_span") as mock_export:
        latencyx.init(app=app, exporters=["console"], enabled=False)
        client = app.test_client()
        client.get("/ping")

        assert not mock_export.called
        assert config.enabled is False


def test_flask_auto_detected_not_fastapi():
    """init() must not apply FastAPI middleware to a Flask app."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/ping")
    def ping():
        return {}

    with patch("latencyx.instrumentors.fastapi.instrument_fastapi") as mock_fa:
        latencyx.init(app=app, exporters=["console"], instrument_http_client=False)
        assert not mock_fa.called
