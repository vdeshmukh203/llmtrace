"""Tests for llmtrace."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from llmtrace import Llmtrace, JSONBackend, SQLiteBackend


# ---------------------------------------------------------------------------
# Basic span recording
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


def test_span_timestamps_set():
    t = Llmtrace()
    s = t.span("m", "p", "r")
    assert s.started_at
    assert s.ended_at


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_span_empty_model_raises():
    t = Llmtrace()
    with pytest.raises(ValueError, match="model"):
        t.span("", "p", "r")


def test_span_none_prompt_raises():
    t = Llmtrace()
    with pytest.raises(ValueError, match="prompt"):
        t.span("gpt-4o", None, "r")


def test_trace_empty_model_raises():
    t = Llmtrace()
    with pytest.raises(ValueError, match="model"):
        with t.trace("", "p"):
            pass


# ---------------------------------------------------------------------------
# Context-manager API
# ---------------------------------------------------------------------------

def test_trace_context_manager():
    t = Llmtrace()
    with t.trace("gpt-4o", "What is 2+2?") as span:
        span.response = "4"
    assert span.response == "4"
    assert span.duration_ms >= 0
    assert span.started_at
    assert span.ended_at


def test_trace_timing_recorded():
    import time
    t = Llmtrace()
    with t.trace("gpt-4o", "slow call") as span:
        time.sleep(0.05)
        span.response = "done"
    assert span.duration_ms >= 40  # at least 40 ms


def test_trace_saved_to_backend():
    t = Llmtrace()
    with t.trace("gpt-4o", "hello") as span:
        span.response = "hi"
    assert len(t.spans()) == 1
    assert t.spans()[0].response == "hi"


def test_trace_with_metadata():
    t = Llmtrace()
    with t.trace("gpt-4o", "p", metadata={"user": "alice"}) as span:
        span.response = "r"
    assert t.spans()[0].metadata["user"] == "alice"


def test_trace_with_parent():
    t = Llmtrace()
    with t.trace("gpt-4o", "parent") as parent:
        parent.response = "p-resp"
    with t.trace("gpt-4o", "child", parent_id=parent.id) as child:
        child.response = "c-resp"
    assert child.parent_id == parent.id


# ---------------------------------------------------------------------------
# Filtering
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


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export():
    t = Llmtrace()
    t.span("m", "p", "r", duration_ms=42)
    ex = t.export()
    assert isinstance(ex, list)
    assert ex[0]["model"] == "m"
    assert ex[0]["duration_ms"] == 42


def test_span_from_dict_roundtrip():
    from llmtrace import Span
    t = Llmtrace()
    s = t.span("m", "prompt text", "response text")
    d = s.to_dict()
    s2 = Span.from_dict(d)
    assert s2.id == s.id
    assert s2.model == s.model
    assert s2.prompt == s.prompt


# ---------------------------------------------------------------------------
# Cost and token estimates
# ---------------------------------------------------------------------------

def test_cost_estimate():
    t = Llmtrace()
    t.span("m", "a" * 500, "b" * 500)
    assert t.cost_estimate(price_per_1k_tokens=0.002) > 0


def test_token_estimate_property():
    from llmtrace import Span
    from datetime import datetime, timezone
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    s = Span(id=str(uuid.uuid4()), model="m", prompt="a" * 400, response="b" * 400,
             started_at=now, ended_at=now, duration_ms=0.0)
    assert s.token_estimate == 200


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

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
    assert s["models"] == {}


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

def test_clear():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.clear()
    assert t.spans() == []


# ---------------------------------------------------------------------------
# JSON backend
# ---------------------------------------------------------------------------

def test_json_backend_persist_and_reload():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.jsonl"
        t = Llmtrace(backend=JSONBackend(path))
        t.span("gpt-4o", "hello", "world", duration_ms=10)

        t2 = Llmtrace(backend=JSONBackend(path))
        spans = t2.spans()
        assert len(spans) == 1
        assert spans[0].model == "gpt-4o"
        assert spans[0].prompt == "hello"


def test_json_backend_clear():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.jsonl"
        t = Llmtrace(backend=JSONBackend(path))
        t.span("m", "p", "r")
        t.clear()
        t2 = Llmtrace(backend=JSONBackend(path))
        assert t2.spans() == []


def test_json_backend_context_manager():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.jsonl"
        t = Llmtrace(backend=JSONBackend(path))
        with t.trace("gpt-4o", "cm test") as span:
            span.response = "ok"

        t2 = Llmtrace(backend=JSONBackend(path))
        spans = t2.spans()
        assert len(spans) == 1
        assert spans[0].response == "ok"


def test_json_backend_missing_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nonexistent.jsonl"
        t = Llmtrace(backend=JSONBackend(path))
        assert t.spans() == []


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

def test_sqlite_backend_persist_and_reload():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.db"
        t = Llmtrace(backend=SQLiteBackend(path))
        t.span("claude-3", "prompt", "response", duration_ms=55)

        t2 = Llmtrace(backend=SQLiteBackend(path))
        spans = t2.spans()
        assert len(spans) == 1
        assert spans[0].model == "claude-3"
        assert spans[0].duration_ms == 55


def test_sqlite_backend_clear():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.db"
        t = Llmtrace(backend=SQLiteBackend(path))
        t.span("m", "p", "r")
        t.clear()
        t2 = Llmtrace(backend=SQLiteBackend(path))
        assert t2.spans() == []


def test_sqlite_backend_metadata_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.db"
        t = Llmtrace(backend=SQLiteBackend(path))
        t.span("m", "p", "r", metadata={"temperature": 0.9, "seed": 42})

        t2 = Llmtrace(backend=SQLiteBackend(path))
        spans = t2.spans()
        assert spans[0].metadata["temperature"] == 0.9
        assert spans[0].metadata["seed"] == 42


def test_sqlite_backend_context_manager():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.db"
        t = Llmtrace(backend=SQLiteBackend(path))
        with t.trace("gpt-4o", "sqlite cm") as span:
            span.response = "persisted"

        t2 = Llmtrace(backend=SQLiteBackend(path))
        spans = t2.spans()
        assert len(spans) == 1
        assert spans[0].response == "persisted"
