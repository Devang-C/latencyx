import time

import httpx
from flask import Flask, jsonify

import latencyx

app = Flask(__name__)

# SQLite is the default exporter — traces land in latencyx_traces.db.
# Add "json_file" to exporters if you want a JSONL file alongside it.
latencyx.init(
    app=app,
    exporters=["sqlite", "console"],
    time_unit="ms",
    instrument_http_client=True,
    min_duration_ms=0.0,
)


@app.get("/")
def root():
    time.sleep(0.05)
    return jsonify({"hello": "world"})


@app.get("/external")
def call_external():
    # HTTP client calls are automatically traced
    with httpx.Client() as client:
        client.get("https://api.github.com/users/github")
    return jsonify({"status": "ok"})


@app.get("/custom")
def custom_trace():
    # Manual instrumentation for custom operations
    with latencyx.timed("custom_operation", span_type="business_logic"):
        time.sleep(0.1)
    return jsonify({"status": "done"})


@app.get("/items/<int:item_id>")
def get_item(item_id: int):
    # Route template /items/<int:item_id> is recorded, not /items/42
    return jsonify({"id": item_id})


if __name__ == "__main__":
    app.run(debug=True, port=8001)
