# LatencyX

**Add one line. Know why your API is slow.**

LatencyX auto-instruments your Python web app and stores traces locally — no Jaeger, no Kafka, no Docker Compose file with 11 services. Just run your app and start asking questions.

> **Status:** Built for local development and staging. Not production-ready yet — see [Production](#production) below.

---

## What you get

- **FastAPI and Flask** middleware — every request traced automatically
- **SQLAlchemy tracing** — sync and async, query names, durations, parent linking
- **httpx tracing** — outbound HTTP calls captured as child spans
- **Local SQLite storage** — no external infra, traces survive restarts
- **CLI analysis tools** — p50/p95/p99, slowest endpoints, error grouping, full trace trees

---

## Quick start

```bash
pip install latencyx
```

```python
from fastapi import FastAPI
import latencyx

app = FastAPI()
latencyx.init(app)  # done
```

That's it. Every request is now traced and stored in `latencyx_traces.db`.

---

## CLI

The CLI is where LatencyX earns its keep. All commands read from the local SQLite database.

### `latencyx stats`
Overall p50/p95/p99 latency, error rate, and top slow endpoints.

```
┌─────────────────────────────────────────────────────────────────┐
│                        LatencyX Stats                           │
├────────────────────────┬───────┬───────┬────────┬──────────────┤
│ Endpoint               │  p50  │  p95  │   p99  │  Error Rate  │
├────────────────────────┼───────┼───────┼────────┼──────────────┤
│ GET /api/users         │ 42ms  │ 310ms │ 890ms  │    1.2%      │
│ POST /api/orders       │ 120ms │ 540ms │ 1200ms │    3.8%      │
│ GET /api/products      │ 18ms  │  65ms │  140ms │    0.0%      │
└────────────────────────┴───────┴───────┴────────┴──────────────┘
```

### `latencyx slowest`
The slowest recent requests, filterable by path and time range.

```
latencyx slowest --limit 10 --path /api/orders
```

### `latencyx errors`
Recent errors grouped by endpoint and message with counts.

### `latencyx endpoints`
All distinct paths with request count, p50/p95, and error rate.

### `latencyx trace <trace_id>`
Full trace tree — HTTP span with child DB query spans and durations.

```
GET /api/orders  412ms  [200]
├── db.query  SELECT orders  180ms
├── db.query  SELECT products  95ms
└── http.client  GET payments.internal/validate  130ms
```

### `latencyx report`
Request volume, error rate, top slow endpoints, top errors — all in one view.

### `latencyx tail`
Live stream of incoming traces as they happen.

---

## Flask

```python
from flask import Flask
import latencyx

app = Flask(__name__)
latencyx.init(app)
```

---

## SQLAlchemy

```python
from sqlalchemy import create_engine
import latencyx

engine = create_engine("sqlite:///myapp.db")
latencyx.init(app, sqlalchemy_engine=engine)
```

Async engines (`create_async_engine`) work the same way.

---

## Optional dependencies

```bash
pip install latencyx               # FastAPI + Flask + CLI
pip install latencyx[http]         # + httpx tracing
pip install latencyx[sqlalchemy]   # + SQLAlchemy tracing
pip install latencyx[all]          # everything
```

---

## Disable with zero overhead

```python
latencyx.init(app, enabled=False)
```

When disabled, all instrumentation is skipped at the entry point — no branches, no storage, no cost.

---

## Production

LatencyX is **not production-ready yet.** It's designed for local development and staging environments.

Specific gaps for production use:

- **Multi-process deployments** (gunicorn with multiple workers) — SQLite does not handle concurrent writes from multiple OS processes reliably under load. You'll get contention or dropped spans.
- **No retention / cleanup** — the trace database grows indefinitely. There's no auto-delete yet.
- **No performance benchmarks** — the per-request overhead hasn't been measured under load.
- **No migration story** — a schema change on upgrade could break an existing database.

For single-process, low-traffic deployments (one uvicorn worker, internal tools, staging) it works fine in practice. For anything beyond that, wait for v1.0.0.

---

## Compared to OpenTelemetry

| | LatencyX | OpenTelemetry |
|---|---|---|
| Setup | 1 line | 50+ lines of config |
| Infrastructure | None (local SQLite) | Collector + backend required |
| Learning curve | Minutes | Hours to days |
| Best for | Dev, staging, small teams | Large-scale, multi-service |

LatencyX isn't trying to replace OpenTelemetry. If you need distributed tracing across 20 microservices, use OTel. If you want to know why your endpoint is slow without standing up infrastructure, use LatencyX.

---

## Roadmap

v0.3.0 is the current release.

v1.0.0 targets: Django support, Redis tracing, SQLite retention/cleanup, performance benchmarks, and a production guide.

---

## License

MIT
