"""Tests for llmtrace."""
import time

import pytest

from llmtrace import Llmtrace, TraceContext


# ---------------------------------------------------------------------------
# Span (manual recording)
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


def test_span_parent():
    t = Llmtrace()
    parent = t.span("gpt-4o", "p", "r")
    child = t.span("gpt-4o", "p2", "r2", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_span_metadata():
    t = Llmtrace()
    s = t.span("m", "p", "r", metadata={"temp": 0.7})
    assert s.metadata["temp"] == 0.7


def test_span_invalid_model_empty():
    t = Llmtrace()
    with pytest.raises(ValueError, match="model"):
        t.span("", "p", "r")


def test_span_invalid_model_type():
    t = Llmtrace()
    with pytest.raises(ValueError, match="model"):
        t.span(42, "p", "r")  # type: ignore[arg-type]


def test_span_invalid_prompt_type():
    t = Llmtrace()
    with pytest.raises(TypeError, match="prompt"):
        t.span("m", 123, "r")  # type: ignore[arg-type]


def test_span_invalid_response_type():
    t = Llmtrace()
    with pytest.raises(TypeError, match="response"):
        t.span("m", "p", ["not", "a", "string"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TraceContext (automatic timing)
# ---------------------------------------------------------------------------

def test_trace_context_type():
    t = Llmtrace()
    assert isinstance(t.trace("gpt-4o"), TraceContext)


def test_trace_records_span():
    t = Llmtrace()
    with t.trace("gpt-4o") as ctx:
        ctx.prompt = "What is 2+2?"
        ctx.response = "4"
    assert len(t.spans()) == 1
    s = t.spans()[0]
    assert s.model == "gpt-4o"
    assert s.prompt == "What is 2+2?"
    assert s.response == "4"


def test_trace_span_accessible_on_context():
    t = Llmtrace()
    with t.trace("gpt-4o") as ctx:
        ctx.prompt = "p"
        ctx.response = "r"
    assert ctx.span is not None
    assert ctx.span is t.spans()[0]


def test_trace_timing_positive():
    t = Llmtrace()
    with t.trace("gpt-4o") as ctx:
        time.sleep(0.01)
        ctx.prompt = "p"
        ctx.response = "r"
    assert ctx.span.duration_ms >= 5  # at least 5 ms for a 10 ms sleep


def test_trace_timestamps_differ():
    t = Llmtrace()
    with t.trace("gpt-4o") as ctx:
        time.sleep(0.01)
        ctx.prompt = "p"
        ctx.response = "r"
    assert ctx.span.started_at != ctx.span.ended_at


def test_trace_metadata_forwarded():
    t = Llmtrace()
    with t.trace("gpt-4o", metadata={"temperature": 0.5}) as ctx:
        ctx.prompt = "p"
        ctx.response = "r"
    assert t.spans()[0].metadata["temperature"] == 0.5


def test_trace_parent_id_forwarded():
    t = Llmtrace()
    root = t.span("gpt-4o", "p", "r")
    with t.trace("gpt-4o", parent_id=root.id) as ctx:
        ctx.prompt = "child prompt"
        ctx.response = "child response"
    assert ctx.span.parent_id == root.id


def test_trace_exception_still_records_span():
    t = Llmtrace()
    with pytest.raises(RuntimeError):
        with t.trace("gpt-4o") as ctx:
            ctx.prompt = "p"
            raise RuntimeError("boom")
    assert len(t.spans()) == 1
    assert t.spans()[0].response == ""


# ---------------------------------------------------------------------------
# Filter
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


def test_filter_no_args_returns_all():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.span("m2", "p", "r")
    assert len(t.filter()) == 2


# ---------------------------------------------------------------------------
# Export, cost, summary, clear
# ---------------------------------------------------------------------------

def test_export():
    t = Llmtrace()
    t.span("m", "p", "r", duration_ms=42)
    ex = t.export()
    assert isinstance(ex, list)
    assert ex[0]["model"] == "m"
    assert ex[0]["duration_ms"] == 42


def test_cost_estimate():
    t = Llmtrace()
    t.span("m", "a" * 500, "b" * 500)
    assert t.cost_estimate(price_per_1k_chars=0.002) > 0


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
# JSON persistence
# ---------------------------------------------------------------------------

def test_save_load_json_roundtrip(tmp_path):
    t = Llmtrace()
    t.span("gpt-4o", "hello", "world", duration_ms=50, metadata={"k": "v"})
    path = str(tmp_path / "spans.json")
    t.save_json(path)

    t2 = Llmtrace()
    t2.load_json(path)
    assert len(t2.spans()) == 1
    s = t2.spans()[0]
    assert s.model == "gpt-4o"
    assert s.prompt == "hello"
    assert s.duration_ms == 50
    assert s.metadata["k"] == "v"


def test_load_json_appends(tmp_path):
    t = Llmtrace()
    t.span("gpt-4o", "p", "r")
    path = str(tmp_path / "spans.json")
    t.save_json(path)

    t2 = Llmtrace()
    t2.span("claude-3", "p", "r")
    t2.load_json(path)
    assert len(t2.spans()) == 2


def test_load_json_missing_file(tmp_path):
    t = Llmtrace()
    with pytest.raises(FileNotFoundError):
        t.load_json(str(tmp_path / "nonexistent.json"))


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------

def test_save_load_sqlite_roundtrip(tmp_path):
    t = Llmtrace()
    parent = t.span("claude-3", "hi", "there", duration_ms=100, metadata={"x": 1})
    t.span("claude-3", "child", "resp", parent_id=parent.id)
    path = str(tmp_path / "spans.db")
    t.save_sqlite(path)

    t2 = Llmtrace()
    t2.load_sqlite(path)
    assert len(t2.spans()) == 2
    s = t2.spans()[0]
    assert s.model == "claude-3"
    assert s.metadata["x"] == 1
    assert t2.spans()[1].parent_id == parent.id


def test_load_sqlite_appends(tmp_path):
    t = Llmtrace()
    t.span("gpt-4o", "p", "r")
    path = str(tmp_path / "spans.db")
    t.save_sqlite(path)

    t2 = Llmtrace()
    t2.span("claude-3", "p", "r")
    t2.load_sqlite(path)
    assert len(t2.spans()) == 2


def test_sqlite_upsert_on_duplicate_id(tmp_path):
    """Saving twice should not duplicate rows (INSERT OR REPLACE)."""
    t = Llmtrace()
    t.span("m", "p", "r")
    path = str(tmp_path / "spans.db")
    t.save_sqlite(path)
    t.save_sqlite(path)  # second save — same IDs

    t2 = Llmtrace()
    t2.load_sqlite(path)
    assert len(t2.spans()) == 1
