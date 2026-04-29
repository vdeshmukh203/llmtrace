"""Tests for llmtrace."""
import json
import time
import pytest
from llmtrace import Llmtrace, Span


# ── Basic span recording ──────────────────────────────────────────────────────

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


def test_span_timestamps_differ_when_duration_nonzero():
    t = Llmtrace()
    s = t.span("m", "p", "r", duration_ms=500)
    assert s.started_at != s.ended_at


def test_span_timestamps_equal_when_duration_zero():
    t = Llmtrace()
    s = t.span("m", "p", "r", duration_ms=0.0)
    assert s.started_at == s.ended_at


def test_span_id_is_uuid_string():
    t = Llmtrace()
    s = t.span("m", "p", "r")
    assert isinstance(s.id, str) and len(s.id) == 36


def test_span_parent():
    t = Llmtrace()
    parent = t.span("gpt-4o", "p", "r")
    child = t.span("gpt-4o", "p2", "r2", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_span_metadata():
    t = Llmtrace()
    s = t.span("m", "p", "r", metadata={"temp": 0.7})
    assert s.metadata["temp"] == 0.7


def test_span_metadata_isolation():
    """Mutating the original dict must not affect the stored span."""
    t = Llmtrace()
    meta = {"k": 1}
    s = t.span("m", "p", "r", metadata=meta)
    meta["k"] = 99
    assert s.metadata["k"] == 1


def test_span_repr():
    t = Llmtrace()
    s = t.span("gpt-4o", "p", "r")
    r = repr(s)
    assert "gpt-4o" in r
    assert "Span(" in r


def test_llmtrace_repr():
    t = Llmtrace()
    t.span("m", "p", "r")
    assert "1" in repr(t)


# ── Input validation ──────────────────────────────────────────────────────────

def test_span_empty_model_raises():
    t = Llmtrace()
    with pytest.raises(ValueError, match="model"):
        t.span("", "p", "r")


def test_span_negative_duration_raises():
    t = Llmtrace()
    with pytest.raises(ValueError, match="duration_ms"):
        t.span("m", "p", "r", duration_ms=-1)


def test_trace_empty_model_raises():
    t = Llmtrace()
    with pytest.raises(ValueError, match="model"):
        t.trace("", "p")


def test_cost_estimate_negative_price_raises():
    t = Llmtrace()
    t.span("m", "p", "r")
    with pytest.raises(ValueError, match="price_per_1k_chars"):
        t.cost_estimate(price_per_1k_chars=-1)


# ── Context manager (trace) ───────────────────────────────────────────────────

def test_trace_records_span():
    t = Llmtrace()
    with t.trace("gpt-4o", "hello") as ctx:
        ctx.response = "world"
    assert len(t.spans()) == 1
    assert t.spans()[0].model == "gpt-4o"
    assert t.spans()[0].response == "world"


def test_trace_measures_duration():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        time.sleep(0.05)
        ctx.response = "r"
    assert t.spans()[0].duration_ms >= 40


def test_trace_timestamps_differ():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        time.sleep(0.01)
        ctx.response = "r"
    s = t.spans()[0]
    assert s.started_at != s.ended_at


def test_trace_context_span_attribute():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        ctx.response = "r"
    assert ctx.span is not None
    assert ctx.span is t.spans()[0]


def test_trace_records_error_in_metadata():
    t = Llmtrace()
    with pytest.raises(RuntimeError):
        with t.trace("m", "p") as ctx:
            raise RuntimeError("boom")
    assert "error" in t.spans()[0].metadata
    assert "RuntimeError" in t.spans()[0].metadata["error"]


def test_trace_with_parent_id():
    t = Llmtrace()
    parent = t.span("m", "p", "r")
    with t.trace("m", "p2", parent_id=parent.id) as ctx:
        ctx.response = "r2"
    assert t.spans()[1].parent_id == parent.id


def test_trace_with_metadata():
    t = Llmtrace()
    with t.trace("m", "p", metadata={"env": "test"}) as ctx:
        ctx.response = "r"
    assert t.spans()[0].metadata["env"] == "test"


# ── Filtering ─────────────────────────────────────────────────────────────────

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
    t.span("gpt-4o", "p", "r", duration_ms=50)
    t.span("gpt-4o", "p", "r", duration_ms=300)
    t.span("claude-3", "p", "r", duration_ms=400)
    result = t.filter(model="gpt-4o", min_duration_ms=200)
    assert len(result) == 1
    assert result[0].duration_ms == 300


def test_filter_no_criteria_returns_all():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.span("m2", "p", "r")
    assert len(t.filter()) == 2


# ── Export and persistence ────────────────────────────────────────────────────

def test_export():
    t = Llmtrace()
    t.span("m", "p", "r", duration_ms=42)
    ex = t.export()
    assert isinstance(ex, list)
    assert ex[0]["model"] == "m"
    assert ex[0]["duration_ms"] == 42


def test_export_contains_all_fields():
    t = Llmtrace()
    p = t.span("m", "prompt_text", "response_text",
                metadata={"k": "v"}, duration_ms=10)
    ex = t.export()[0]
    for key in ("id", "model", "prompt", "response", "started_at",
                "ended_at", "duration_ms", "metadata", "parent_id"):
        assert key in ex


def test_span_from_dict_roundtrip():
    t = Llmtrace()
    original = t.span("m", "p", "r", duration_ms=7.5, metadata={"x": 1})
    restored = Span.from_dict(original.to_dict())
    assert restored.id == original.id
    assert restored.duration_ms == original.duration_ms
    assert restored.metadata == original.metadata


def test_save_and_load_json(tmp_path):
    path = str(tmp_path / "spans.json")
    t1 = Llmtrace()
    t1.span("m", "hello", "world", duration_ms=50)
    t1.save_json(path)

    t2 = Llmtrace()
    t2.load_json(path)
    assert len(t2.spans()) == 1
    assert t2.spans()[0].model == "m"
    assert t2.spans()[0].prompt == "hello"
    assert t2.spans()[0].duration_ms == 50.0


def test_load_json_appends(tmp_path):
    path = str(tmp_path / "spans.json")
    t = Llmtrace()
    t.span("m", "p", "r")
    t.save_json(path)

    t.load_json(path)
    assert len(t.spans()) == 2


def test_load_json_invalid_file(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w") as f:
        json.dump({"not": "a list"}, f)
    t = Llmtrace()
    with pytest.raises(ValueError, match="JSON array"):
        t.load_json(path)


# ── Aggregation ───────────────────────────────────────────────────────────────

def test_cost_estimate():
    t = Llmtrace()
    t.span("m", "a" * 500, "b" * 500)
    assert t.cost_estimate(price_per_1k_chars=0.002) > 0


def test_cost_estimate_zero_when_no_spans():
    t = Llmtrace()
    assert t.cost_estimate() == 0.0


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
    assert s["total_duration_ms"] == 0.0
    assert s["avg_duration_ms"] == 0.0
    assert s["models"] == {}
    assert s["cost_estimate"] == 0.0


def test_summary_multi_model():
    t = Llmtrace()
    t.span("gpt-4o", "p", "r", duration_ms=100)
    t.span("claude-3", "p", "r", duration_ms=200)
    s = t.summary()
    assert s["count"] == 2
    assert "gpt-4o" in s["models"]
    assert "claude-3" in s["models"]


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def test_clear():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.clear()
    assert t.spans() == []


def test_spans_returns_copy():
    """Mutating the returned list must not affect internal state."""
    t = Llmtrace()
    t.span("m", "p", "r")
    result = t.spans()
    result.clear()
    assert len(t.spans()) == 1
