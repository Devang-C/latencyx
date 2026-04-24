import time

import pytest

from latencyx.config import ExporterType, config
from latencyx.core import Span, init, timed

# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------


def test_span_has_span_id_and_trace_id():
    span = Span("test")
    assert isinstance(span.span_id, str) and len(span.span_id) == 32
    assert isinstance(span.trace_id, str) and len(span.trace_id) == 32


def test_span_has_started_at_as_unix_epoch():
    import time

    before = time.time()
    span = Span("test")
    after = time.time()
    assert before <= span.started_at <= after


def test_child_span_inherits_trace_id():
    """All spans within the same timed() nesting share a trace_id."""
    with timed("parent") as parent_span:
        with timed("child") as child_span:
            pass
    assert parent_span is not None and child_span is not None
    assert parent_span.trace_id == child_span.trace_id
    assert child_span.parent is parent_span


def test_root_span_generates_unique_trace_id():
    with timed("a") as span_a:
        pass
    with timed("b") as span_b:
        pass
    assert span_a is not None and span_b is not None
    assert span_a.trace_id != span_b.trace_id


def test_span_records_duration():
    span = Span("test")
    time.sleep(0.01)
    span.finish()
    assert span.duration_ms is not None
    assert span.duration_ms >= 10.0


def test_span_finish_skips_when_disabled():
    config.enabled = False
    span = Span("test")
    span.finish()
    assert span.duration_ms is None  # finish() returned early


def test_span_finish_skips_below_min_duration(tmp_path):
    config.min_duration_ms = 9999.0
    config.exporters = [ExporterType.JSON_FILE]
    config.json_file_path = str(tmp_path / "traces.jsonl")

    from latencyx.exporters import init_exporters

    init_exporters()

    span = Span("fast_op")
    span.finish()

    lines = (tmp_path / "traces.jsonl").read_text().splitlines()
    assert lines == []


def test_span_records_error():
    span = Span("test")
    span.finish(error=ValueError("boom"))
    assert span.error == "boom"


def test_span_records_traceback_when_enabled():
    config.include_traceback = True
    span = Span("test")
    try:
        raise RuntimeError("oops")
    except RuntimeError as e:
        span.finish(error=e)
    assert span.traceback is not None


# ---------------------------------------------------------------------------
# timed()
# ---------------------------------------------------------------------------


def test_timed_yields_span():
    with timed("op") as span:
        assert span is not None
        assert span.name == "op"


def test_timed_default_span_type():
    with timed("op") as span:
        assert span.span_type == "generic"  # type: ignore[union-attr]


def test_timed_custom_span_type():
    with timed("op", span_type="db.query") as span:
        assert span.span_type == "db.query"  # type: ignore[union-attr]


def test_timed_custom_metadata():
    with timed("op", metadata={"key": "value"}) as span:
        assert span.metadata["key"] == "value"  # type: ignore[union-attr]


def test_timed_records_duration():
    with timed("op") as span:
        time.sleep(0.015)
    assert span.duration_ms >= 15.0  # type: ignore[union-attr]


def test_timed_captures_and_reraises_exception():
    with pytest.raises(ValueError):
        with timed("op") as span:
            raise ValueError("test error")
    assert span.error == "test error"  # type: ignore[union-attr]


def test_timed_disabled_yields_none():
    config.enabled = False
    with timed("op") as span:
        assert span is None


def test_timed_zero_sample_rate_yields_none():
    config.sample_rate = 0.0
    with timed("op") as span:
        assert span is None


def test_timed_full_sample_rate_always_samples():
    config.sample_rate = 1.0
    with timed("op") as span:
        assert span is not None


def test_timed_nested_spans_restore_parent():
    with timed("parent") as parent_span:
        with timed("child") as child_span:
            assert child_span is not None
            assert child_span.parent == parent_span
        # After exiting child, current_span should be back to parent
        from latencyx.core import _current_span_var

        assert _current_span_var.get() == parent_span


# ---------------------------------------------------------------------------
# init()
# ---------------------------------------------------------------------------


def test_init_converts_string_exporters():
    init(exporters=["console"])
    assert ExporterType.CONSOLE in config.exporters


def test_init_converts_string_time_unit():
    from latencyx.config import TimeUnit

    init(time_unit="s")
    assert config.time_unit == TimeUnit.SECONDS


def test_init_respects_enabled_false():
    # init() must not override enabled=False — that would defeat the fast-path
    init(enabled=False)
    assert config.enabled is False


def test_init_enabled_by_default():
    # Without an explicit enabled=False, init() leaves enabled as True (the default)
    init()
    assert config.enabled is True


def test_init_invalid_sample_rate_raises():
    with pytest.raises(ValueError, match="sample_rate"):
        init(sample_rate=1.5)

    with pytest.raises(ValueError, match="sample_rate"):
        init(sample_rate=-0.1)


def test_init_valid_sample_rate_boundaries():
    init(sample_rate=0.0)
    assert config.sample_rate == 0.0

    init(sample_rate=1.0)
    assert config.sample_rate == 1.0


def test_init_ignores_unknown_kwargs():
    init(nonexistent_option="whatever")  # should not raise


def test_init_sets_custom_json_path(tmp_path):
    path = str(tmp_path / "custom.jsonl")
    init(exporters=["json_file"], json_file_path=path)
    assert config.json_file_path == path
