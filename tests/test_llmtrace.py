"""Tests for llmtrace."""
import json
import os
import tempfile
import time

import pytest

from llmtrace import Llmtrace, Span


# ------------------------------------------------------------------ #
# Span basics                                                          #
# ------------------------------------------------------------------ #

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


def test_span_repr():
    t = Llmtrace()
    s = t.span("gpt-4o", "hello", "world")
    r = repr(s)
    assert "gpt-4o" in r
    assert "duration_ms" in r


def test_span_to_dict_round_trip():
    t = Llmtrace()
    s = t.span("m", "prompt text", "resp text", duration_ms=55.5, metadata={"k": 1})
    d = s.to_dict()
    s2 = Span.from_dict(d)
    assert s2.id == s.id
    assert s2.model == s.model
    assert s2.duration_ms == s.duration_ms
    assert s2.metadata == s.metadata


# ------------------------------------------------------------------ #
# trace() context manager                                              #
# ------------------------------------------------------------------ #

def test_trace_context_manager_records_span():
    t = Llmtrace()
    with t.trace("gpt-4o", "hello") as ctx:
        ctx.response = "world"
    assert len(t.spans()) == 1
    s = t.spans()[0]
    assert s.model == "gpt-4o"
    assert s.prompt == "hello"
    assert s.response == "world"


def test_trace_measures_duration():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        time.sleep(0.02)
        ctx.response = "r"
    s = t.spans()[0]
    assert s.duration_ms >= 15


def test_trace_started_before_ended():
    t = Llmtrace()
    with t.trace("m", "p") as ctx:
        ctx.response = "r"
    s = t.spans()[0]
    assert s.started_at <= s.ended_at


def test_trace_records_on_exception():
    t = Llmtrace()
    with pytest.raises(ValueError):
        with t.trace("m", "p") as ctx:
            raise ValueError("boom")
    assert len(t.spans()) == 1
    assert t.spans()[0].response == ""


def test_trace_parent_id():
    t = Llmtrace()
    with t.trace("m", "parent") as p:
        p.response = "pr"
    with t.trace("m", "child", parent_id=t.spans()[0].id) as c:
        c.response = "cr"
    assert t.spans()[1].parent_id == t.spans()[0].id


# ------------------------------------------------------------------ #
# Filtering                                                            #
# ------------------------------------------------------------------ #

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
    t.span("gpt-4o", "p", "r", duration_ms=500)
    t.span("claude-3", "p", "r", duration_ms=500)
    result = t.filter(model="gpt-4o", min_duration_ms=100)
    assert len(result) == 1
    assert result[0].duration_ms == 500


# ------------------------------------------------------------------ #
# Export                                                               #
# ------------------------------------------------------------------ #

def test_export():
    t = Llmtrace()
    t.span("m", "p", "r", duration_ms=42)
    ex = t.export()
    assert isinstance(ex, list)
    assert ex[0]["model"] == "m"
    assert ex[0]["duration_ms"] == 42


# ------------------------------------------------------------------ #
# JSON persistence                                                     #
# ------------------------------------------------------------------ #

def test_save_and_load_json():
    t = Llmtrace()
    t.span("gpt-4o", "hello", "world", duration_ms=10, metadata={"x": 1})
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        t.save_json(path)
        t2 = Llmtrace()
        t2.load_json(path)
        assert len(t2.spans()) == 1
        s = t2.spans()[0]
        assert s.model == "gpt-4o"
        assert s.prompt == "hello"
        assert s.duration_ms == 10.0
        assert s.metadata == {"x": 1}
    finally:
        os.unlink(path)


def test_save_json_is_valid_json():
    t = Llmtrace()
    t.span("m", "p", "r")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
    try:
        t.save_json(path)
        with open(path) as fh:
            data = json.load(fh)
        assert isinstance(data, list)
    finally:
        os.unlink(path)


# ------------------------------------------------------------------ #
# SQLite persistence                                                   #
# ------------------------------------------------------------------ #

def test_save_and_load_sqlite():
    t = Llmtrace()
    t.span("claude-3", "ask", "answer", duration_ms=99, metadata={"y": 2})
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        t.save_sqlite(path)
        t2 = Llmtrace()
        t2.load_sqlite(path)
        assert len(t2.spans()) == 1
        s = t2.spans()[0]
        assert s.model == "claude-3"
        assert s.duration_ms == 99.0
        assert s.metadata == {"y": 2}
    finally:
        os.unlink(path)


def test_sqlite_upsert():
    """Saving the same tracer twice should not duplicate rows."""
    t = Llmtrace()
    t.span("m", "p", "r")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        t.save_sqlite(path)
        t.save_sqlite(path)
        t2 = Llmtrace()
        t2.load_sqlite(path)
        assert len(t2.spans()) == 1
    finally:
        os.unlink(path)


# ------------------------------------------------------------------ #
# Analytics                                                            #
# ------------------------------------------------------------------ #

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
    assert s["total_duration_ms"] == 0.0


def test_clear():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.clear()
    assert t.spans() == []
