# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Always use the `.venv` in the project root. Never use system Python.

```bash
.venv/bin/python   # interpreter
uv pip install -e ".[dev]"  # install/sync deps
```

## Commands

```bash
# Lint (must be clean before committing)
.venv/bin/ruff check .
.venv/bin/ruff check . --fix   # auto-fix

# Format (must be clean before committing)
.venv/bin/ruff format .
.venv/bin/ruff format --check .   # check only

# Type check
.venv/bin/mypy latencyx/

# Run all tests (with coverage)
.venv/bin/pytest

# Run a single test file or test
.venv/bin/pytest tests/test_core.py
.venv/bin/pytest tests/test_core.py::test_timed_yields_span

# Run the example app
.venv/bin/uvicorn example_app:app --reload
```

## After every code change

Run these before committing — CI will fail if they don't pass:

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format . && .venv/bin/mypy latencyx/ && .venv/bin/pytest
```

Pre-commit hooks (`ruff check --fix` + `ruff format`) run automatically on `git commit`. They auto-fix what they can and fail the commit if files were changed — just `git add` and commit again.

## Commits

Concise, lowercase, imperative. One line. No period at the end.

```
# Good
fix route template resolution in fastapi middleware
add sqlalchemy instrumentor
bump version to 0.2.0

# Bad
Fixed the bug where route templates weren't being resolved correctly in the FastAPI middleware instrumentation
```

## Pull Requests

Follow the format in `.github/PULL_REQUEST_TEMPLATE.md` when opening PRs with `gh pr create`. See that file for the exact structure.

## Architecture

LatencyX is a zero-config observability library. The public API is just two functions: `latencyx.init(app)` and `latencyx.timed(name)`.

**Data flow:**

```
User code / middleware
        │
   core.timed()          ← context manager, creates Span, handles sampling
        │
    Span.finish()        ← applies min_duration filter, collects error/traceback
        │
  exporters.export_span() ← fans out to all configured exporters
        │
  ┌─────┴──────┐
ConsoleExporter  JsonFileExporter   (more coming)
```

**Key files:**
- `latencyx/config.py` — single global `config` singleton (`LatencyXConfig` dataclass). All behaviour is driven by this object.
- `latencyx/core.py` — `Span` class and `timed()` context manager. Thread-local `_LocalState` tracks the current span for parent/child relationships. `init()` lives here too and wires everything together.
- `latencyx/exporters/` — factory in `__init__.py`, one class per exporter. Adding a new exporter means adding a class here and a new `ExporterType` enum value in `config.py`.
- `latencyx/instrumentors/` — auto-instrumentation via middleware (FastAPI) and monkey-patching (httpx). `instrument_fastapi()` adds `LatencyMiddleware`; `instrument_http_client()` wraps `httpx.Client.request` with a threading lock to prevent double-patching.
- `latencyx/cli.py` — standalone `latencyx tail` command that reads and pretty-prints the JSONL trace file.

**Global state to be aware of in tests:**
- `latencyx.config.config` — mutated by `init()`. The `reset_latencyx_state` autouse fixture in `tests/conftest.py` saves and restores all fields after each test.
- `latencyx.exporters._exporters` — rebuilt by `init_exporters()` using assignment (not `.clear()`), so always access it via the module reference (`import latencyx.exporters as m; m._exporters`) rather than importing the list directly.
- `latencyx.instrumentors.http_client._original_httpx_request` — set on first `instrument_http_client()` call. The conftest fixture undoes the monkey-patch after tests that trigger it.
