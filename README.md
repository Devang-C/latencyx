# LatencyX

**Lightweight auto-instrumentation for Python web apps. Because OpenTelemetry made you question your life choices.**

Built for solo developers and small teams who want observability without needing a PhD in distributed systems.

## Why LatencyX?

- **One-line setup** - `latencyx.init(app)` and you're done
- **Auto-instrumentation** - FastAPI, HTTP clients (httpx). More coming.
- **Multiple exporters** - Console, JSON files
- **Minimal dependencies** - Won't break your deployment
- **Actually simple** - No 50-page configuration docs

## Quick Start

```bash
pip install latencyx
```

```python
from fastapi import FastAPI
import latencyx

app = FastAPI()
latencyx.init(app)  # That's it.

@app.get("/")
async def root():
    return {"hello": "world"}
```

**Output:**
```
INFO:latencyx:[http.server] GET / duration=50.58ms status=200 method=GET client=127.0.0.1 path=/
```

### CLI Monitoring

Watch your traces in real-time with a pretty CLI:

```bash
latencyx tail
```

```
📊 Watching LatencyX traces from: latencyx_traces.jsonl
   Press Ctrl+C to stop
──────────────────────────────────────────────────────────────────────────────────────
TYPE             │ NAME                            │    DURATION │   STATUS │ DETAILS
──────────────────────────────────────────────────────────────────────────────────────
http.server      │ GET /                           │     50.58ms │      200 │ client=127.0.0.1
http.client      │ GET api.github.com/users/github │     656.2ms │      200 │ host=api.github.com
http.server      │ GET /external                   │     662.0ms │      200 │ client=127.0.0.1
business_logic   │ custom_operation                │     100.2ms │  success │
http.server      │ GET /custom                     │     101.1ms │      200 │ client=127.0.0.1
```

It's basically `tail -f` but doesn't hurt your eyes.

## What Gets Traced?

- **FastAPI endpoints** (automatic)
- **HTTP client calls** via httpx (automatic)
- **Custom operations** via context managers

For advanced usage, configuration options, and examples, see USAGE.md in the repository.

## Comparison with OpenTelemetry

| Feature | LatencyX | OpenTelemetry |
|---------|----------|---------------|
| Setup | 1 line | 50+ lines |
| Dependencies | Minimal | Heavy |
| Learning curve | Minutes | Hours/Days |
| Best for | Solo devs, small teams | Large enterprises |

LatencyX isn't trying to replace OpenTelemetry. If you need distributed tracing across 50 microservices, use OTel. If you just want to know why your API is slow, use LatencyX.

## Roadmap

| Feature | Status | Notes |
|---------|--------|-------|
| FastAPI instrumentation | ✓ Done | Works today |
| HTTP client tracing (httpx) | ✓ Done | Works today |
| Console & JSON exporters | ✓ Done | Works today |
| Flask instrumentation | Planned | Because not everyone uses FastAPI |
| SQLAlchemy support | Planned | Async + sync |
| PostgreSQL (psycopg2, asyncpg) | Planned | Native drivers |
| Redis tracing | Planned | Cache tracing that doesn't lie |
| MySQL support | Planned | For the other half |
| Async jobs (Celery, RQ) | Planned | Background tasks need love too |

**Vote for these by opening an issue:**

| Feature | Why it's in maybe-land |
|---------|------------------------|
| Distributed tracing with trace IDs | Complex, needs real use cases |
| WebSocket tracing | Depends on demand |
| Sentry/Datadog integration | Only if people actually need it |
| Slow query detection | Might build if requested |
| APM tool integrations | Tell me which ones matter |

If something here would make your life easier, let me know. Otherwise, it stays in maybe-land.

## Contributing

This is a solo project right now, but contributions are welcome:

- **Feature requests** - Open an issue and tell me what you need
- **Bug reports** - If something breaks, let me know
- **Code contributions** - PRs welcome, but let's keep it simple

No formal process yet. Just open an issue or PR.

## Installation

```bash
# Basic installation
pip install latencyx

# With optional dependencies
pip install latencyx[http]      # HTTP client tracing
pip install latencyx[all]       # Everything
```

## License

MIT License - use it however you want.

---

**Made for developers who want observability without the headache.**