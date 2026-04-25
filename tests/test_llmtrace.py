"""Tests for llmtrace."""
import pytest
from llmtrace import Llmtrace


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


def test_clear():
    t = Llmtrace()
    t.span("m", "p", "r")
    t.clear()
    assert t.spans() == []
