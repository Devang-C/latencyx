# LatencyX Roadmap

**Goal:** Fastest path from "my app is slow" to "I know why." Zero friction, no infra, no PhD required.

**Target audience:** Solo devs and small teams who want observability without setting up OTel + Jaeger + Docker just to see what's happening.

---

## v0.2.0 — Stabilize ✅ released

- [x] Add test suite (pytest) — unit tests for core, config, exporters; integration test with a real FastAPI app
- [x] Set up GitHub Actions CI — run tests + lint (ruff) on every push/PR
- [x] Automate PyPI publish via GitHub Actions on `v*` tag push (replace `deploy.sh`)
- [x] Fix `datetime.utcnow()` → `datetime.now(UTC)` for Python 3.12+ compatibility
- [x] Delete dead code — `exporters/logging.py`, `archived/` directory, commented-out psycopg2/redis refs
- [x] Replace `print()` with `logger.warning()` in exporter failure paths
- [x] Ensure instrumentation failures can never crash the host app (explicit guards around monkey-patching)

---

## v0.3.0 — Expand

Cover the stack that small teams actually run.

- [ ] Add SQLite exporter as the default local storage
- [ ] Add `enabled=False` fast-path that skips all instrumentation (zero overhead when disabled)
- [ ] Flask instrumentation
- [ ] SQLAlchemy tracing (sync + async)
- [ ] Django middleware support
- [ ] `latencyx stats` CLI command — p50/p95/p99, error rate, top slow endpoints (reads from SQLite)
- [ ] `latencyx slowest` CLI command — filter by time range, path, status
- [ ] Slow query/span auto-tagging — automatically flag spans above a configurable threshold

---

## v1.0.0 — Polish (Week 3)

Something you'd confidently recommend to another team.

- [ ] Redis tracing — completes the typical small-team stack (FastAPI + SQLAlchemy + Redis)
- [ ] SQLite retention config — auto-delete traces older than N days
- [ ] `latencyx check` CLI command — verify the library is running and connected correctly
- [ ] Production guide in docs — overhead, what can go wrong, recommended config
- [ ] Performance benchmarks — teams need to know the cost before adding to prod
- [ ] Update README and USAGE.md to reflect all new features and frameworks

---

## Database Design

### Shipped (schema v2)

- [x] SQLite as default local storage (`latencyx_traces.db`); JSONL kept for log shippers
- [x] WAL mode for better concurrent write performance
- [x] Schema versioning (`schema_version` table) — foundation for future migrations
- [x] Trace/span ID linking — `trace_id` (shared per request), `span_id`, `parent_span_id`
- [x] `service_name` column — filter traces by service (set via `config.service_name`)
- [x] `started_at` as Unix epoch alongside ISO timestamp — fast time-range queries
- [x] `url` column for http.client spans
- [x] Indexes on `timestamp`, `started_at`, `duration_ms`, `trace_id`, `path`, `status_code`, `service_name`

### Future

- [ ] Migrations framework — when the first real user exists on an older schema, ship a separate migration script rather than auto-migrating in the exporter
- [ ] Auto-delete spans older than N days + `VACUUM` to reclaim disk space (v1.0.0)
- [ ] `environment` column (`dev` / `staging` / `prod`) — add when there's real demand
- [ ] Pre-aggregated stats table (p50/p95/p99 per endpoint) — only needed at ~500k+ rows

---

## Maybe Later

Features that stay in maybe-land until there's real demand. Open an issue to vote.

- [ ] Local web UI — `latencyx serve` spins up a browser dashboard with charts
- [ ] Celery / RQ async job tracing
- [ ] WebSocket tracing
- [ ] Distributed trace IDs across services
- [ ] Sentry / Datadog exporter (for teams that outgrow local storage)
- [ ] MySQL / asyncpg / psycopg2 database tracing