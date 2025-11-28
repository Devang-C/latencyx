# LatencyX Usage Guide

Detailed documentation for configuration, exporters, and advanced usage.

## Installation Options

```bash
# Basic (FastAPI support only)
pip install latencyx

# With HTTP client tracing
pip install latencyx[http]

# Everything
pip install latencyx[all]
```

## Configuration

### Full Options

```python
import latencyx

latencyx.init(
    app=app,
    
    # Exporters
    exporters=["console", "json_file"],
    
    # Time format
    time_unit="ms",  # or "s"
    
    # File export
    json_file_path="./traces.jsonl",
    
    # Auto-instrumentation
    instrument_fastapi=True,
    instrument_http_client=True,
    
    # Filtering
    min_duration_ms=10.0,  # Only log requests > 10ms
    sample_rate=1.0,  # 1.0 = 100%, 0.1 = 10%
    
    # Error handling
    include_traceback=False,  # Include stack traces on errors
)
```

### Minimal Setup

```python
latencyx.init(app)  # Uses sensible defaults
```

## What Gets Traced?

### FastAPI Endpoints (Automatic)

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}

# Traces: "GET /users/{user_id}"
```

### HTTP Client Calls (Automatic)

Requires httpx:

```python
import httpx

with httpx.Client() as client:
    response = client.get("https://api.example.com/data")

# Traces: "GET api.example.com/data"
```

### Custom Operations

```python
import latencyx

with latencyx.timed("process_payment", span_type="business_logic") as span:
    process_payment(user_id, amount)
    
    # Add metadata
    span.metadata["amount"] = amount
    span.metadata["user_id"] = user_id

# Traces: "process_payment" with custom metadata
```

## Exporters

### Console Exporter

Logs to stdout via Python logging:

```
INFO:latencyx:[http.server] GET / duration=50.58ms status=200 method=GET client=127.0.0.1 path=/
```

Good for development and debugging.

### JSON File Exporter

Writes newline-delimited JSON:

```json
{"timestamp": "2025-11-27T04:51:28.507074", "span_name": "custom_operation", "span_type": "business_logic", "duration_ms": 100.117, "status": "success"}
{"timestamp": "2025-11-27T04:51:28.508113", "span_name": "GET /custom", "span_type": "http.server", "duration_ms": 101.35, "status": "success", "method": "GET", "path": "/custom", "status_code": 200}
{"timestamp": "2025-11-27T04:51:40.636894", "span_name": "GET api.github.com/users/github", "span_type": "http.client", "duration_ms": 289.527, "status": "success", "method": "GET", "url": "https://api.github.com/users/github", "status_code": 200}
```

Works with log aggregation tools like Loki, CloudWatch, Datadog.

## Common Use Cases

### Development - Show Only Slow Requests

```python
latencyx.init(
    app=app,
    exporters=["console"],
    min_duration_ms=50.0,
)
```

### Production - Sample and Export

```python
latencyx.init(
    app=app,
    exporters=["json_file"],
    json_file_path="/var/log/app/traces.jsonl",
    sample_rate=0.1,  # 10% sampling
)
```

### Local Testing - See Everything

```python
latencyx.init(
    app=app,
    exporters=["console"],
    include_traceback=True,
)
```

## Advanced Usage

### Nested Spans

```python
with latencyx.timed("parent_operation"):
    with latencyx.timed("child_operation_1"):
        do_something()
    
    with latencyx.timed("child_operation_2"):
        do_something_else()
```

### Error Tracking

Errors are automatically captured:

```python
with latencyx.timed("risky_operation") as span:
    raise ValueError("Something went wrong")

# Trace includes: "error": "Something went wrong"
```

### Custom Metadata

```python
with latencyx.timed("db_query", span_type="db.query") as span:
    result = db.execute("SELECT * FROM users")
    span.metadata["rows_returned"] = len(result)
```

## Filtering

### Duration Filtering

Only log operations that take longer than a threshold:

```python
latencyx.init(app, min_duration_ms=100.0)  # Only > 100ms
```

### Sampling

Sample a percentage of requests:

```python
latencyx.init(app, sample_rate=0.1)  # 10% of requests
```

## Tips

- Use `console` exporter in development
- Use `json_file` exporter in production
- Set `min_duration_ms` to filter out noise
- Use sampling in high-traffic production environments
- Add custom metadata to track business metrics

## Limitations

- No distributed tracing (yet)
- No database instrumentation (yet - coming soon)
- Console exporter uses Python logging (might not play nice with your logger setup)

## Contributing

Found a bug? Want a feature? Open an issue on GitHub.

Want to contribute code? PRs welcome. Keep it simple.

## License

MIT