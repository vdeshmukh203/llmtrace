"""LLM call tracer with timing, filtering, storage, and export."""
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """A single recorded LLM API call."""

    id: str
    model: str
    prompt: str
    response: str
    started_at: str
    ended_at: str
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of this span."""
        return {
            "id": self.id,
            "model": self.model,
            "prompt": self.prompt,
            "response": self.response,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "parent_id": self.parent_id,
        }


class TraceContext:
    """Context manager that wraps an LLM call and records wall-clock timing.

    Obtain an instance via :meth:`Llmtrace.trace` and set *prompt* and
    *response* inside the ``with`` block.  The finished :class:`Span` is
    appended to the tracer on exit and is accessible via ``ctx.span``.

    Example::

        with tracer.trace("gpt-4o") as ctx:
            ctx.prompt = "Summarise this document."
            ctx.response = llm_call(ctx.prompt)
        print(ctx.span.duration_ms)
    """

    def __init__(
        self,
        tracer: "Llmtrace",
        model: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> None:
        self._tracer = tracer
        self.model = model
        self.prompt: str = ""
        self.response: str = ""
        self.metadata: Dict[str, Any] = metadata or {}
        self.parent_id = parent_id
        self.span: Optional[Span] = None
        self._started_at: Optional[datetime] = None
        self._t0: Optional[float] = None

    def __enter__(self) -> "TraceContext":
        self._started_at = datetime.now(timezone.utc)
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = round((time.monotonic() - self._t0) * 1000, 3)  # type: ignore[operator]
        ended_at = datetime.now(timezone.utc)
        self.span = Span(
            id=str(uuid.uuid4()),
            model=self.model,
            prompt=self.prompt,
            response=self.response,
            started_at=self._started_at.isoformat(),  # type: ignore[union-attr]
            ended_at=ended_at.isoformat(),
            duration_ms=duration_ms,
            metadata=self.metadata,
            parent_id=self.parent_id,
        )
        self._tracer._spans.append(self.span)
        return False  # never suppress exceptions


class Llmtrace:
    """Collector for LLM API call spans.

    Usage (manual)::

        tracer = Llmtrace()
        tracer.span("gpt-4o", prompt, response, duration_ms=123)

    Usage (context manager with automatic timing)::

        with tracer.trace("gpt-4o") as ctx:
            ctx.prompt = "Hello!"
            ctx.response = llm_call(ctx.prompt)
    """

    def __init__(self) -> None:
        self._spans: List[Span] = []

    # ------------------------------------------------------------------ record

    def span(
        self,
        model: str,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        parent_id: Optional[str] = None,
    ) -> Span:
        """Record a completed LLM span.

        Use this method when you already have the prompt, response, and
        duration (e.g. after wrapping a call manually).  For automatic
        wall-clock timing use :meth:`trace` instead.

        :param model: Model identifier (e.g. ``"gpt-4o"``).
        :param prompt: Input text sent to the model.
        :param response: Text returned by the model.
        :param metadata: Optional key/value annotations.
        :param duration_ms: Elapsed time in milliseconds.
        :param parent_id: UUID of a parent span for hierarchical traces.
        :raises ValueError: If *model* is not a non-empty string.
        :raises TypeError: If *prompt* or *response* is not a string.
        """
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        if not isinstance(response, str):
            raise TypeError("response must be a string")
        now = datetime.now(timezone.utc).isoformat()
        s = Span(
            id=str(uuid.uuid4()),
            model=model,
            prompt=prompt,
            response=response,
            started_at=now,
            ended_at=now,
            duration_ms=duration_ms,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        self._spans.append(s)
        return s

    def trace(
        self,
        model: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> TraceContext:
        """Return a context manager that captures wall-clock timing automatically.

        :param model: Model identifier (e.g. ``"gpt-4o"``).
        :param metadata: Optional key/value annotations forwarded to the span.
        :param parent_id: UUID of a parent span for hierarchical traces.

        Example::

            with tracer.trace("gpt-4o", metadata={"temperature": 0.7}) as ctx:
                ctx.prompt = "What is 2 + 2?"
                ctx.response = llm_call(ctx.prompt)
        """
        return TraceContext(self, model, metadata=metadata, parent_id=parent_id)

    # ------------------------------------------------------------------ query

    def spans(self) -> List[Span]:
        """Return a copy of all recorded spans in insertion order."""
        return list(self._spans)

    def filter(
        self,
        model: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        has_parent: Optional[bool] = None,
    ) -> List[Span]:
        """Return spans matching all supplied criteria.

        :param model: Keep only spans whose model equals this value.
        :param min_duration_ms: Keep only spans with ``duration_ms >= min_duration_ms``.
        :param has_parent: If ``True`` keep only child spans; if ``False`` keep only roots.
        """
        result: List[Span] = list(self._spans)
        if model is not None:
            result = [s for s in result if s.model == model]
        if min_duration_ms is not None:
            result = [s for s in result if s.duration_ms >= min_duration_ms]
        if has_parent is not None:
            result = [s for s in result if (s.parent_id is not None) == has_parent]
        return result

    def export(self) -> List[Dict[str, Any]]:
        """Export all spans as a list of JSON-serialisable dicts."""
        return [s.to_dict() for s in self._spans]

    def cost_estimate(self, price_per_1k_chars: float = 0.002) -> float:
        """Rough cost estimate based on total prompt + response character count.

        :param price_per_1k_chars: USD per 1 000 characters (default: 0.002).
        """
        total = sum(len(s.prompt) + len(s.response) for s in self._spans)
        return round((total / 1000) * price_per_1k_chars, 6)

    def summary(self) -> Dict[str, Any]:
        """Return aggregate statistics across all recorded spans.

        Keys: ``count``, ``total_duration_ms``, ``avg_duration_ms``,
        ``models`` (dict of model → count), ``cost_estimate``.
        """
        if not self._spans:
            return {"count": 0, "total_duration_ms": 0.0, "models": {}}
        models: Dict[str, int] = {}
        for s in self._spans:
            models[s.model] = models.get(s.model, 0) + 1
        total_ms = sum(s.duration_ms for s in self._spans)
        return {
            "count": len(self._spans),
            "total_duration_ms": total_ms,
            "avg_duration_ms": round(total_ms / len(self._spans), 2),
            "models": models,
            "cost_estimate": self.cost_estimate(),
        }

    def clear(self) -> None:
        """Remove all recorded spans."""
        self._spans.clear()

    # --------------------------------------------------------------- JSON I/O

    def save_json(self, path: str) -> None:
        """Write all spans to a JSON file at *path* (overwrites if present)."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.export(), fh, indent=2)

    def load_json(self, path: str) -> None:
        """Append spans from a JSON file at *path* to the current tracer.

        Duplicate span IDs are not deduplicated; call :meth:`clear` first
        if a clean reload is desired.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for d in data:
            self._spans.append(Span(**d))

    # ------------------------------------------------------------- SQLite I/O

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS spans (
            id          TEXT PRIMARY KEY,
            model       TEXT NOT NULL,
            prompt      TEXT NOT NULL,
            response    TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            ended_at    TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            metadata    TEXT NOT NULL,
            parent_id   TEXT
        )
    """

    def save_sqlite(self, path: str) -> None:
        """Write all spans to a SQLite database at *path*.

        Creates the database and ``spans`` table if they do not exist.
        Existing rows with the same ``id`` are replaced (upsert semantics).
        """
        con = sqlite3.connect(path)
        try:
            con.execute(self._CREATE_TABLE)
            con.executemany(
                "INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        s.id, s.model, s.prompt, s.response,
                        s.started_at, s.ended_at, s.duration_ms,
                        json.dumps(s.metadata), s.parent_id,
                    )
                    for s in self._spans
                ],
            )
            con.commit()
        finally:
            con.close()

    def load_sqlite(self, path: str) -> None:
        """Append spans from a SQLite database at *path* to the current tracer.

        Duplicate span IDs are not deduplicated; call :meth:`clear` first
        if a clean reload is desired.
        """
        con = sqlite3.connect(path)
        try:
            rows = con.execute(
                "SELECT id, model, prompt, response, started_at, ended_at,"
                "       duration_ms, metadata, parent_id FROM spans"
            ).fetchall()
        finally:
            con.close()
        for row in rows:
            self._spans.append(
                Span(
                    id=row[0], model=row[1], prompt=row[2], response=row[3],
                    started_at=row[4], ended_at=row[5], duration_ms=row[6],
                    metadata=json.loads(row[7]), parent_id=row[8],
                )
            )
