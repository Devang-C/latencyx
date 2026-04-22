import logging
import time

# import psycopg2  # Archived for v1
import httpx
from fastapi import FastAPI

import latencyx

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# SQLite is the default exporter — traces land in latencyx_traces.db.
# Add "json_file" to exporters if you want a JSONL file alongside it
# (useful for piping to other tools or log shippers).
latencyx.init(
    app=app,
    exporters=["sqlite", "console"],
    time_unit="ms",
    instrument_http_client=True,
    min_duration_ms=0.0,
)


@app.get("/")
async def root():
    time.sleep(0.05)
    return {"hello": "world"}


@app.get("/external")
async def call_external():
    # HTTP client calls are automatically traced
    with httpx.Client() as client:
        client.get("https://api.github.com/users/github")
    return {"status": "ok"}


@app.get("/custom")
async def custom_trace():
    # Manual instrumentation for custom operations
    with latencyx.timed("custom_operation", span_type="business_logic"):
        time.sleep(0.1)
        # Your custom logic here
    return {"status": "done"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("example_app:app", host="0.0.0.0", port=8000, reload=True)
