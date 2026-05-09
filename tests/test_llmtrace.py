"""Tests for llmtrace core, backends, and dashboard."""
import json
import os
import threading
import time
from urllib.request import urlopen

import pytest

from llmtrace import Llmtrace, JsonBackend, SqliteBackend, Span


# ---------------------------------------------------------------------------
# Span dataclass
# ---------------------------------------------------------------------------

class TestSpan:
    def test_to_dict_roundtrip(self):
        s = Span(
            id="abc", model="gpt-4o", prompt="hi", response="hello",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:00.310+00:00",
            duration_ms=310.0,
            metadata={"temp": 0.7},
            parent_id="parent-123",
        )
        d = s.to_dict()
        assert d["id"] == "abc"
        assert d["model"] == "gpt-4o"
        assert d["prompt"] == "hi"
        assert d["response"] == "hello"
        assert d["duration_ms"] == 310.0
        assert d["metadata"] == {"temp": 0.7}
        assert d["parent_id"] == "parent-123"

    def test_default_metadata_is_empty_dict(self):
        s = Span("x", "m", "p", "r", "t", "t", 0.0)
        assert s.metadata == {}
        assert s.parent_id is None


# ---------------------------------------------------------------------------
# Llmtrace.span — manual recording
# ---------------------------------------------------------------------------

class TestManualSpan:
    def test_basic_fields(self):
        t = Llmtrace()
        s = t.span("gpt-4o", "hello", "world")
        assert s.model == "gpt-4o"
        assert s.prompt == "hello"
        assert s.response == "world"
        assert s.id  # non-empty UUID string

    def test_duration_stored(self):
        t = Llmtrace()
        s = t.span("gpt-4o", "p", "r", duration_ms=123.4)
        assert s.duration_ms == 123.4

    def test_parent_id(self):
        t = Llmtrace()
        parent = t.span("gpt-4o", "p", "r")
        child = t.span("gpt-4o", "p2", "r2", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_metadata_stored(self):
        t = Llmtrace()
        s = t.span("m", "p", "r", metadata={"temp": 0.7})
        assert s.metadata["temp"] == 0.7

    def test_metadata_default_empty(self):
        t = Llmtrace()
        s = t.span("m", "p", "r")
        assert s.metadata == {}

    def test_invalid_empty_model(self):
        t = Llmtrace()
        with pytest.raises(ValueError, match="model"):
            t.span("", "p", "r")

    def test_invalid_prompt_type(self):
        t = Llmtrace()
        with pytest.raises(TypeError, match="prompt"):
            t.span("m", 123, "r")  # type: ignore[arg-type]

    def test_invalid_response_type(self):
        t = Llmtrace()
        with pytest.raises(TypeError, match="response"):
            t.span("m", "p", None)  # type: ignore[arg-type]

    def test_negative_duration_raises(self):
        t = Llmtrace()
        with pytest.raises(ValueError, match="duration_ms"):
            t.span("m", "p", "r", duration_ms=-1)

    def test_started_at_and_ended_at_are_set(self):
        t = Llmtrace()
        s = t.span("m", "p", "r")
        assert s.started_at
        assert s.ended_at


# ---------------------------------------------------------------------------
# Llmtrace.trace — context-manager API
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_span_is_created_on_exit(self):
        t = Llmtrace()
        with t.trace("gpt-4o", prompt="hi") as ctx:
            ctx.response = "hello"
        assert ctx.span is not None
        assert ctx.span.model == "gpt-4o"
        assert ctx.span.prompt == "hi"
        assert ctx.span.response == "hello"

    def test_duration_is_positive(self):
        t = Llmtrace()
        with t.trace("m", prompt="p") as ctx:
            time.sleep(0.01)
            ctx.response = "r"
        assert ctx.span.duration_ms >= 10

    def test_started_at_before_ended_at(self):
        t = Llmtrace()
        with t.trace("m") as ctx:
            time.sleep(0.005)
            ctx.response = "r"
        assert ctx.span.started_at < ctx.span.ended_at

    def test_span_appended_to_tracer(self):
        t = Llmtrace()
        with t.trace("m", prompt="p") as ctx:
            ctx.response = "r"
        assert len(t.spans()) == 1
        assert t.spans()[0] is ctx.span

    def test_metadata_enrichment_inside_block(self):
        t = Llmtrace()
        with t.trace("m") as ctx:
            ctx.response = "r"
            ctx.metadata["tokens"] = 42
        assert ctx.span.metadata["tokens"] == 42

    def test_parent_id_propagated(self):
        t = Llmtrace()
        with t.trace("m") as root:
            root.response = "r"
        with t.trace("m", parent_id=root.span.id) as child:
            child.response = "c"
        assert child.span.parent_id == root.span.id

    def test_exception_propagates_span_still_recorded(self):
        t = Llmtrace()
        with pytest.raises(ValueError):
            with t.trace("m", prompt="p") as ctx:
                ctx.response = "partial"
                raise ValueError("boom")
        assert len(t.spans()) == 1
        assert t.spans()[0].response == "partial"

    def test_empty_model_raises(self):
        t = Llmtrace()
        with pytest.raises(ValueError, match="model"):
            t.trace("")


# ---------------------------------------------------------------------------
# Filter, export, summary, clear
# ---------------------------------------------------------------------------

class TestQueryAPI:
    def test_filter_by_model(self):
        t = Llmtrace()
        t.span("gpt-4o", "p", "r")
        t.span("claude-3", "p", "r")
        assert len(t.filter(model="gpt-4o")) == 1
        assert len(t.filter(model="claude-3")) == 1
        assert len(t.filter(model="unknown")) == 0

    def test_filter_by_duration(self):
        t = Llmtrace()
        t.span("m", "p", "r", duration_ms=10)
        t.span("m", "p", "r", duration_ms=200)
        assert len(t.filter(min_duration_ms=100)) == 1
        assert len(t.filter(min_duration_ms=5)) == 2
        assert len(t.filter(min_duration_ms=201)) == 0

    def test_filter_has_parent(self):
        t = Llmtrace()
        p = t.span("m", "p", "r")
        t.span("m", "p2", "r2", parent_id=p.id)
        assert len(t.filter(has_parent=True)) == 1
        assert len(t.filter(has_parent=False)) == 1

    def test_filter_combined(self):
        t = Llmtrace()
        t.span("gpt-4o", "p", "r", duration_ms=50)
        t.span("gpt-4o", "p", "r", duration_ms=500)
        t.span("claude-3", "p", "r", duration_ms=600)
        result = t.filter(model="gpt-4o", min_duration_ms=100)
        assert len(result) == 1
        assert result[0].duration_ms == 500

    def test_export_structure(self):
        t = Llmtrace()
        t.span("m", "p", "r", duration_ms=42)
        ex = t.export()
        assert isinstance(ex, list)
        assert ex[0]["model"] == "m"
        assert ex[0]["duration_ms"] == 42
        assert "id" in ex[0]
        assert "started_at" in ex[0]

    def test_cost_estimate(self):
        t = Llmtrace()
        t.span("m", "a" * 500, "b" * 500)
        cost = t.cost_estimate(price_per_1k_chars=0.002)
        assert cost == pytest.approx((1000 / 1000) * 0.002, rel=1e-4)

    def test_cost_estimate_negative_price_raises(self):
        t = Llmtrace()
        with pytest.raises(ValueError, match="price_per_1k_chars"):
            t.cost_estimate(-1)

    def test_summary_empty(self):
        t = Llmtrace()
        s = t.summary()
        assert s["count"] == 0
        assert s["total_duration_ms"] == 0.0
        assert s["models"] == {}

    def test_summary_populated(self):
        t = Llmtrace()
        t.span("gpt-4o", "p", "r", duration_ms=50)
        t.span("gpt-4o", "p", "r", duration_ms=100)
        s = t.summary()
        assert s["count"] == 2
        assert s["avg_duration_ms"] == 75.0
        assert s["models"]["gpt-4o"] == 2
        assert "cost_estimate" in s

    def test_clear(self):
        t = Llmtrace()
        t.span("m", "p", "r")
        t.clear()
        assert t.spans() == []

    def test_spans_returns_copy(self):
        t = Llmtrace()
        t.span("m", "p", "r")
        lst = t.spans()
        lst.clear()
        assert len(t.spans()) == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_span_writes(self):
        t = Llmtrace()
        n = 200
        errors = []

        def worker():
            try:
                t.span("m", "p", "r", duration_ms=1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors
        assert len(t.spans()) == n

    def test_concurrent_trace_context(self):
        t = Llmtrace()
        n = 100
        errors = []

        def worker():
            try:
                with t.trace("m") as ctx:
                    time.sleep(0.001)
                    ctx.response = "ok"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors
        assert len(t.spans()) == n


# ---------------------------------------------------------------------------
# JsonBackend
# ---------------------------------------------------------------------------

class TestJsonBackend:
    def test_append_and_load(self, tmp_path):
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        s1 = _make_span("m1")
        b.append(s1)
        loaded = b.load()
        assert len(loaded) == 1
        assert loaded[0].id == s1.id
        assert loaded[0].model == "m1"

    def test_multiple_appends(self, tmp_path):
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        for i in range(5):
            b.append(_make_span(f"m{i}"))
        assert len(b.load()) == 5

    def test_save_overwrites(self, tmp_path):
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        b.append(_make_span("old"))
        b.save([_make_span("new1"), _make_span("new2")])
        loaded = b.load()
        assert len(loaded) == 2
        assert loaded[0].model == "new1"

    def test_save_empty_clears(self, tmp_path):
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        b.append(_make_span("m"))
        b.save([])
        assert b.load() == []

    def test_load_missing_file_raises(self, tmp_path):
        b = JsonBackend(str(tmp_path / "nope.json"))
        with pytest.raises(FileNotFoundError):
            b.load()

    def test_atomic_write(self, tmp_path):
        """tmp file should not linger after a successful write."""
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        b.append(_make_span("m"))
        assert not os.path.exists(path + ".tmp")

    def test_metadata_roundtrip(self, tmp_path):
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        s = _make_span("m", metadata={"k": "v", "n": 3})
        b.append(s)
        assert b.load()[0].metadata == {"k": "v", "n": 3}

    def test_tracer_integration(self, tmp_path):
        path = str(tmp_path / "spans.json")
        b = JsonBackend(path)
        t = Llmtrace(backend=b)
        t.span("gpt-4o", "p", "r", duration_ms=10)
        t2 = Llmtrace(backend=JsonBackend(path))
        assert len(t2.spans()) == 1
        assert t2.spans()[0].model == "gpt-4o"


# ---------------------------------------------------------------------------
# SqliteBackend
# ---------------------------------------------------------------------------

class TestSqliteBackend:
    def test_append_and_load(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        s = _make_span("gpt-4o")
        b.append(s)
        loaded = b.load()
        assert len(loaded) == 1
        assert loaded[0].id == s.id

    def test_multiple_appends(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        for i in range(5):
            b.append(_make_span(f"m{i}"))
        assert len(b.load()) == 5

    def test_save_overwrites(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        b.append(_make_span("old"))
        b.save([_make_span("new1"), _make_span("new2")])
        loaded = b.load()
        assert len(loaded) == 2
        assert loaded[0].model == "new1"

    def test_save_empty_clears(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        b.append(_make_span("m"))
        b.save([])
        assert b.load() == []

    def test_in_memory(self):
        b = SqliteBackend(":memory:")
        b.append(_make_span("m"))
        assert len(b.load()) == 1

    def test_upsert_on_duplicate_id(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        s = _make_span("m")
        b.append(s)
        b.append(s)  # same id — should not raise or duplicate
        assert len(b.load()) == 1

    def test_metadata_roundtrip(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        s = _make_span("m", metadata={"key": "value", "num": 42})
        b.append(s)
        assert b.load()[0].metadata == {"key": "value", "num": 42}

    def test_none_parent_id(self, tmp_path):
        b = SqliteBackend(str(tmp_path / "runs.db"))
        s = _make_span("m")
        b.append(s)
        assert b.load()[0].parent_id is None

    def test_tracer_integration(self, tmp_path):
        db = str(tmp_path / "runs.db")
        t = Llmtrace(backend=SqliteBackend(db))
        t.span("claude-3", "p", "r", duration_ms=20)
        t2 = Llmtrace(backend=SqliteBackend(db))
        assert len(t2.spans()) == 1
        assert t2.spans()[0].model == "claude-3"


# ---------------------------------------------------------------------------
# Dashboard (GUI)
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_serves_html(self):
        from llmtrace.gui import Dashboard
        t = Llmtrace()
        t.span("m", "p", "r", duration_ms=10)
        dash = Dashboard(t, port=0)
        dash.start()
        try:
            resp = urlopen(dash.url + "/")
            assert resp.status == 200
            body = resp.read().decode()
            assert "llmtrace" in body
        finally:
            dash.shutdown()

    def test_api_spans_returns_json(self):
        from llmtrace.gui import Dashboard
        t = Llmtrace()
        t.span("gpt-4o", "hello", "hi", duration_ms=42)
        dash = Dashboard(t, port=0)
        dash.start()
        try:
            resp = urlopen(dash.url + "/api/spans")
            data = json.loads(resp.read())
            assert isinstance(data, list)
            assert data[0]["model"] == "gpt-4o"
        finally:
            dash.shutdown()

    def test_api_summary_returns_json(self):
        from llmtrace.gui import Dashboard
        t = Llmtrace()
        t.span("m", "p", "r", duration_ms=100)
        dash = Dashboard(t, port=0)
        dash.start()
        try:
            resp = urlopen(dash.url + "/api/summary")
            data = json.loads(resp.read())
            assert data["count"] == 1
        finally:
            dash.shutdown()

    def test_api_export_content_disposition(self):
        from llmtrace.gui import Dashboard
        t = Llmtrace()
        dash = Dashboard(t, port=0)
        dash.start()
        try:
            resp = urlopen(dash.url + "/api/export")
            cd = resp.headers.get("Content-Disposition", "")
            assert "spans.json" in cd
        finally:
            dash.shutdown()

    def test_url_property(self):
        from llmtrace.gui import Dashboard
        t = Llmtrace()
        dash = Dashboard(t, host="127.0.0.1", port=0)
        dash.start()
        try:
            assert dash.url.startswith("http://127.0.0.1:")
        finally:
            dash.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(model: str, metadata: dict | None = None) -> Span:
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return Span(
        id=str(uuid.uuid4()),
        model=model,
        prompt="test prompt",
        response="test response",
        started_at=now,
        ended_at=now,
        duration_ms=42.0,
        metadata=metadata or {},
    )
