"""LLM call tracer with timing, filtering, and persistent storage."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .backends import _Backend


@dataclass
class Span:
    """Immutable record of a single LLM API call.

    All timestamps are ISO 8601 strings in UTC (``+00:00`` suffix).
    ``duration_ms`` is the wall-clock latency of the call in milliseconds.
    ``metadata`` holds arbitrary caller-supplied key/value pairs.
    ``parent_id`` links this span to a parent span for hierarchical tracing.
    """

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
        """Return a JSON-serialisable dict representation."""
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


class _TraceContext:
    """Context manager that times an LLM call and commits the span on exit.

    Obtain instances via :meth:`Llmtrace.trace`; do not instantiate directly.

    Set :attr:`response` (and optionally enrich :attr:`metadata`) inside the
    ``with`` block.  The span is appended to the tracer—and any configured
    backend—when the block exits, whether or not an exception was raised.

    Example::

        with tracer.trace("gpt-4o", prompt="Explain entropy") as ctx:
            ctx.response = openai_client.complete(ctx.prompt)
            ctx.metadata["tokens"] = 120
        print(ctx.span.duration_ms)
    """

    __slots__ = (
        "model", "prompt", "response", "metadata", "parent_id",
        "_tracer", "_started_at", "span",
    )

    def __init__(
        self,
        tracer: Llmtrace,
        model: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]],
        parent_id: Optional[str],
    ) -> None:
        self._tracer = tracer
        self.model = model
        self.prompt = prompt
        self.response: str = ""
        self.metadata: Dict[str, Any] = metadata if metadata is not None else {}
        self.parent_id = parent_id
        self._started_at: Optional[datetime] = None
        self.span: Optional[Span] = None

    def __enter__(self) -> _TraceContext:
        self._started_at = datetime.now(timezone.utc)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        ended = datetime.now(timezone.utc)
        assert self._started_at is not None  # always set in __enter__
        duration_ms = (ended - self._started_at).total_seconds() * 1_000.0
        self.span = self._tracer._record(
            model=self.model,
            prompt=self.prompt,
            response=self.response,
            started_at=self._started_at.isoformat(),
            ended_at=ended.isoformat(),
            duration_ms=duration_ms,
            metadata=self.metadata,
            parent_id=self.parent_id,
        )
        return False  # never suppress exceptions


class Llmtrace:
    """Thread-safe LLM call tracer with optional persistent storage.

    Parameters
    ----------
    backend:
        Optional storage backend.  Must implement ``append(span: Span)`` and
        ``load() -> List[Span]``.  Use :class:`~llmtrace.backends.JsonBackend`
        or :class:`~llmtrace.backends.SqliteBackend` from
        :mod:`llmtrace.backends`, or supply a custom object.

    Examples
    --------
    Manual span recording::

        tracer = Llmtrace()
        s = tracer.span("gpt-4o", prompt="hi", response="hello", duration_ms=310)

    Automatic timing via context manager::

        with tracer.trace("claude-3-5-sonnet", prompt="Summarise this") as ctx:
            ctx.response = my_llm_call(ctx.prompt)
        print(ctx.span.duration_ms)

    Persistent storage::

        from llmtrace.backends import SqliteBackend
        tracer = Llmtrace(backend=SqliteBackend("runs.db"))
    """

    def __init__(self, backend: Optional[_Backend] = None) -> None:
        self._spans: List[Span] = []
        self._lock = threading.Lock()
        self._backend = backend
        if backend is not None:
            try:
                self._spans = backend.load()
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(
        self,
        model: str,
        prompt: str,
        response: str,
        started_at: str,
        ended_at: str,
        duration_ms: float,
        metadata: Dict[str, Any],
        parent_id: Optional[str],
    ) -> Span:
        s = Span(
            id=str(uuid.uuid4()),
            model=model,
            prompt=prompt,
            response=response,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            metadata=metadata,
            parent_id=parent_id,
        )
        with self._lock:
            self._spans.append(s)
            if self._backend is not None:
                self._backend.append(s)
        return s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trace(
        self,
        model: str,
        prompt: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> _TraceContext:
        """Return a context manager that records a timed span on exit.

        ``started_at``/``ended_at`` and ``duration_ms`` are captured
        automatically from the wall clock; no manual timing is required.

        Parameters
        ----------
        model:
            LLM model identifier, e.g. ``"gpt-4o"`` or ``"claude-3-5-sonnet"``.
        prompt:
            Input text sent to the model (may also be set inside the block).
        metadata:
            Initial metadata dict; may be extended inside the block.
        parent_id:
            ``id`` of the parent span for nested traces.

        Raises
        ------
        ValueError
            If *model* is empty.
        """
        if not model:
            raise ValueError("model must be a non-empty string")
        return _TraceContext(self, model, prompt, metadata, parent_id)

    def span(
        self,
        model: str,
        prompt: str,
        response: str,
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> Span:
        """Record a completed LLM span with caller-supplied timing.

        Prefer :meth:`trace` when you want automatic wall-clock timing.
        Use this method when replaying or importing existing records.

        Parameters
        ----------
        model:
            LLM model identifier.
        prompt:
            Input text sent to the model.
        response:
            Text returned by the model.
        duration_ms:
            Observed latency in milliseconds (must be ≥ 0).
        metadata:
            Arbitrary key/value pairs to attach to the span.
        parent_id:
            ``id`` of a parent span for hierarchical tracing.

        Raises
        ------
        ValueError
            If *model* is empty or *duration_ms* is negative.
        TypeError
            If *prompt* or *response* are not strings.
        """
        if not model:
            raise ValueError("model must be a non-empty string")
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        if not isinstance(response, str):
            raise TypeError("response must be a string")
        if duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        now = datetime.now(timezone.utc).isoformat()
        return self._record(
            model=model,
            prompt=prompt,
            response=response,
            started_at=now,
            ended_at=now,
            duration_ms=duration_ms,
            metadata=metadata if metadata is not None else {},
            parent_id=parent_id,
        )

    def spans(self) -> List[Span]:
        """Return a snapshot list of all recorded spans."""
        with self._lock:
            return list(self._spans)

    def filter(
        self,
        model: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        has_parent: Optional[bool] = None,
    ) -> List[Span]:
        """Return spans matching all supplied criteria (AND semantics).

        Parameters
        ----------
        model:
            Exact model identifier to match (case-sensitive).
        min_duration_ms:
            Include only spans with ``duration_ms >= min_duration_ms``.
        has_parent:
            ``True`` to return only child spans; ``False`` for root spans only.
        """
        with self._lock:
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
        with self._lock:
            return [s.to_dict() for s in self._spans]

    def cost_estimate(self, price_per_1k_chars: float = 0.002) -> float:
        """Rough cost estimate based on combined prompt + response character count.

        Parameters
        ----------
        price_per_1k_chars:
            Cost in USD per 1,000 characters (default 0.002).

        Raises
        ------
        ValueError
            If *price_per_1k_chars* is negative.
        """
        if price_per_1k_chars < 0:
            raise ValueError("price_per_1k_chars must be non-negative")
        with self._lock:
            total = sum(len(s.prompt) + len(s.response) for s in self._spans)
        return round((total / 1_000) * price_per_1k_chars, 6)

    def summary(self) -> Dict[str, Any]:
        """Return aggregate statistics across all recorded spans.

        Returns a dict with keys ``count``, ``total_duration_ms``,
        ``avg_duration_ms`` (omitted when count is 0), ``models``
        (per-model call counts), and ``cost_estimate``.
        """
        with self._lock:
            spans = list(self._spans)
        if not spans:
            return {"count": 0, "total_duration_ms": 0.0, "models": {}}
        models: Dict[str, int] = {}
        for s in spans:
            models[s.model] = models.get(s.model, 0) + 1
        total_ms = sum(s.duration_ms for s in spans)
        return {
            "count": len(spans),
            "total_duration_ms": round(total_ms, 2),
            "avg_duration_ms": round(total_ms / len(spans), 2),
            "models": models,
            "cost_estimate": self.cost_estimate(),
        }

    def clear(self) -> None:
        """Remove all in-memory spans.

        Does **not** delete data from the configured backend; use the
        backend's own ``save([])`` method for that.
        """
        with self._lock:
            self._spans.clear()
