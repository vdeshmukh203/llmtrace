"""Tests for llmtrace."""
import json
import os
import time

import pytest

from llmtrace import JsonBackend, Llmtrace, SQLiteBackend


# ---------------------------------------------------------------------------
# Core — Span recording
# ---------------------------------------------------------------------------

def test_span_basic():
    t = Llmtrace()
    s = t.span("gpt-4o", "hello", "world")
    assert s.model == "gpt-4o"
    assert s.prompt == "hello"
    assert s.response == "world"


def test_span_duration():
    t = Llmtrace()
    s = t.span("gpt-4o", "p", "r", duration_ms=123.4)
    assert s.duration_ms == 123.4


def test_span_timestamps_consistent():
    """started_at must be strictly before or equal to ended_at."""
    t = Llmtrace()
    s = t.span("gpt-4o", "p", "r", duration_ms=500.0)
    assert s.started_at <= s.ended_at
    assert s.started_at != s.ended_at  # non-zero duration produces distinct timestamps


def test_span_zero_duration_timestamps_equal():
    t = Llmtrace()
    s = t.span("gpt-4o", "p", "r", duration_ms=0.0)
    assert s.started_at == s.ended_at


def test_span_parent():
    t = Llmtrace()
    parent = t.span("gpt-4o", "p", "r")
    child = t.span("gpt-4o", "p2", "r2", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_span_metadata():
    t = Llmtrace()
    s = t.span("m", "p", "r", metadata={"temp": 0.7})
    assert s.metadata["temp"] == 0.7


def test_span_default_metadata_is_empty_dict():
    t = Llmtrace()
    s = t.span("m", "p", "r")
    assert s.metadata == {}


def test_span_has_unique_ids():
    t = Llmtrace()
    ids = {t.span("m", "p", "r").id for _ in range(5)}
    assert len(ids) == 5


def test_span_repr():
    t = Llmtrace()
    s = t.span("gpt-4o", "p", "r")
    r = repr(s)
    assert "gpt-4o" in r
    assert "Span(" in r


# ---------------------------------------------------------------------------
# Core — context manager
# ---------------------------------------------------------------------------

def test_trace_context_manager_records_span():
    t = Llmtrace()
    with t.trace("claude-3", "What is 2+2?") as ctx:
        ctx["response"] = "4"
    assert len(t.spans()) == 1
    s = t.spans()[0]
    assert s.model == "claude-3"
    assert s.prompt == "What is 2+2?"
    assert s.response == "4"


def test_trace_context_manager_measures_duration():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        time.sleep(0.05)
        ctx["response"] = "r"
    assert t.spans()[0].duration_ms >= 40  # at least 40 ms


def test_trace_context_manager_timestamps_ordered():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        ctx["response"] = "r"
    s = t.spans()[0]
    assert s.started_at <= s.ended_at


def test_trace_context_manager_records_on_exception():
    """The span must be saved even when the body raises."""
    t = Llmtrace()
    with pytest.raises(ValueError):
        with t.trace("m", "p") as ctx:
            raise ValueError("oops")
    assert len(t.spans()) == 1
    assert t.spans()[0].response == ""


def test_trace_context_manager_supports_metadata_and_parent():
    t = Llmtrace()
    with t.trace("m", "p", metadata={"k": 1}) as ctx:
        ctx["response"] = "r"
    parent_id = t.spans()[0].id
    with t.trace("m", "p2", parent_id=parent_id) as ctx:
        ctx["response"] = "r2"
    assert t.spans()[1].parent_id == parent_id
    assert t.spans()[0].metadata == {"k": 1}


# ---------------------------------------------------------------------------
# Core — filter
# ---------------------------------------------------------------------------

def test_filter_by_model():
    t = Llmtrace()
    t.span("gpt-4o", "p", "r")
    t.span("claude-3", "p", "r")
    assert len(t.filter(model="gpt-4o")) == 1
    assert len(t.filter(model="claude-3")) == 1


def test_filter_by_duration():
    t = Llmtrace()
    t.span("m", "p", "r", duration_ms=10)
    t.span("m", "p", "r", duration_ms=200)
    assert len(t.filter(min_duration_ms=100)) == 1
    assert len(t.filter(min_duration_ms=5)) == 2


def test_filter_has_parent():
    t = Llmtrace()
    p = t.span("m", "p", "r")
    t.span("m", "p2", "r2", parent_id=p.id)
    assert len(t.filter(has_parent=True)) == 1
    assert len(t.filter(has_parent=False)) == 1


def test_filter_combined():
    t = Llmtrace()
    t.span("gpt-4o", "p", "r", duration_ms=10)
    t.span("gpt-4o", "p", "r", duration_ms=200)
    t.span("claude-3", "p", "r", duration_ms=200)
    result = t.filter(model="gpt-4o", min_duration_ms=100)
    assert len(result) == 1
    assert result[0].duration_ms == 200


def test_filter_no_criteria_returns_all():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.span("m", "p", "r")
    assert len(t.filter()) == 2


# ---------------------------------------------------------------------------
# Core — export / summary / cost
# ---------------------------------------------------------------------------

def test_export():
    t = Llmtrace()
    t.span("m", "p", "r", duration_ms=42)
    ex = t.export()
    assert isinstance(ex, list)
    assert ex[0]["model"] == "m"
    assert ex[0]["duration_ms"] == 42


def test_export_is_json_serialisable():
    import json as _json
    t = Llmtrace()
    t.span("m", "p", "r", metadata={"x": [1, 2]})
    _json.dumps(t.export())  # must not raise


def test_cost_estimate():
    t = Llmtrace()
    t.span("m", "a" * 500, "b" * 500)
    assert t.cost_estimate(price_per_1k_chars=0.002) > 0


def test_cost_estimate_scales_with_chars():
    t = Llmtrace()
    t.span("m", "a" * 1000, "b" * 1000)
    cost1 = t.cost_estimate(price_per_1k_chars=0.001)
    cost2 = t.cost_estimate(price_per_1k_chars=0.002)
    assert abs(cost2 - 2 * cost1) < 1e-9


def test_summary():
    t = Llmtrace()
    t.span("gpt-4o", "p", "r", duration_ms=50)
    t.span("gpt-4o", "p", "r", duration_ms=100)
    s = t.summary()
    assert s["count"] == 2
    assert s["avg_duration_ms"] == 75.0
    assert s["models"]["gpt-4o"] == 2


def test_summary_empty():
    t = Llmtrace()
    s = t.summary()
    assert s["count"] == 0
    assert s["models"] == {}


def test_clear():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.clear()
    assert t.spans() == []


# ---------------------------------------------------------------------------
# JsonBackend
# ---------------------------------------------------------------------------

def test_json_backend_roundtrip(tmp_path):
    t = Llmtrace()
    t.span("gpt-4o", "hello", "world", duration_ms=42, metadata={"k": "v"})
    path = str(tmp_path / "spans.json")
    t.save_json(path)

    t2 = Llmtrace()
    t2.load_json(path)
    assert len(t2.spans()) == 1
    s = t2.spans()[0]
    assert s.model == "gpt-4o"
    assert s.prompt == "hello"
    assert s.duration_ms == 42
    assert s.metadata == {"k": "v"}


def test_json_backend_file_is_valid_json(tmp_path):
    t = Llmtrace()
    t.span("m", "p", "r")
    path = str(tmp_path / "out.json")
    t.save_json(path)
    with open(path) as fh:
        data = json.load(fh)
    assert isinstance(data, list)
    assert len(data) == 1


def test_json_backend_load_append(tmp_path):
    t = Llmtrace()
    t.span("m", "p", "r")
    path = str(tmp_path / "spans.json")
    t.save_json(path)

    t2 = Llmtrace()
    t2.span("m", "p2", "r2")
    t2.load_json(path)
    assert len(t2.spans()) == 2


def test_json_backend_preserves_parent_id(tmp_path):
    t = Llmtrace()
    p = t.span("m", "parent", "resp")
    t.span("m", "child", "resp", parent_id=p.id)
    path = str(tmp_path / "spans.json")
    t.save_json(path)

    t2 = Llmtrace()
    t2.load_json(path)
    child = next(s for s in t2.spans() if s.prompt == "child")
    assert child.parent_id == p.id


# ---------------------------------------------------------------------------
# SQLiteBackend
# ---------------------------------------------------------------------------

def test_sqlite_backend_roundtrip(tmp_path):
    t = Llmtrace()
    t.span("claude-3", "hi", "there", duration_ms=77, metadata={"n": 1})
    path = str(tmp_path / "spans.db")
    t.save_sqlite(path)

    t2 = Llmtrace()
    t2.load_sqlite(path)
    assert len(t2.spans()) == 1
    s = t2.spans()[0]
    assert s.model == "claude-3"
    assert s.duration_ms == 77
    assert s.metadata == {"n": 1}


def test_sqlite_backend_upsert(tmp_path):
    """Saving the same span twice should not duplicate it."""
    t = Llmtrace()
    t.span("m", "p", "r")
    path = str(tmp_path / "spans.db")
    t.save_sqlite(path)
    t.save_sqlite(path)

    t2 = Llmtrace()
    t2.load_sqlite(path)
    assert len(t2.spans()) == 1


def test_sqlite_backend_load_append(tmp_path):
    t = Llmtrace()
    t.span("m", "p", "r")
    path = str(tmp_path / "spans.db")
    t.save_sqlite(path)

    t2 = Llmtrace()
    t2.span("m", "p2", "r2")
    t2.load_sqlite(path)
    assert len(t2.spans()) == 2


def test_sqlite_backend_file_created(tmp_path):
    t = Llmtrace()
    t.span("m", "p", "r")
    path = str(tmp_path / "new.db")
    assert not os.path.exists(path)
    t.save_sqlite(path)
    assert os.path.exists(path)
