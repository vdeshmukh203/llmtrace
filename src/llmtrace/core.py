"""LLM call tracer with timing, context-manager API, filtering, and export."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

from .backends import Backend, MemoryBackend


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

    @property
    def token_estimate(self) -> int:
        """Approximate token count using the common 4-chars-per-token rule."""
        return (len(self.prompt) + len(self.response)) // 4

    def to_dict(self) -> Dict[str, Any]:
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

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Span":
        return cls(**d)


class Llmtrace:
    """LLM call tracer with timing, filtering, and pluggable storage backends.

    Parameters
    ----------
    backend:
        Storage backend.  Defaults to :class:`~llmtrace.backends.MemoryBackend`
        (in-process list).  Pass a :class:`~llmtrace.backends.JSONBackend` or
        :class:`~llmtrace.backends.SQLiteBackend` for persistent storage.

    Example
    -------
    In-memory (default)::

        tracer = Llmtrace()
        with tracer.trace("gpt-4o", "Summarise this text") as span:
            span.response = call_llm(span.prompt)

    Persistent JSON log::

        from llmtrace.backends import JSONBackend
        tracer = Llmtrace(backend=JSONBackend("spans.jsonl"))
    """

    def __init__(self, backend: Optional[Backend] = None) -> None:
        self._backend: Backend = backend if backend is not None else MemoryBackend()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

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

        Use this when you already have the response and timing.  For
        automatic timing, prefer the :meth:`trace` context manager.
        """
        if not model:
            raise ValueError("model must be a non-empty string")
        if prompt is None:
            raise ValueError("prompt must not be None")
        now = datetime.now(timezone.utc).isoformat()
        s = Span(
            id=str(uuid.uuid4()),
            model=model,
            prompt=prompt,
            response=response or "",
            started_at=now,
            ended_at=now,
            duration_ms=duration_ms,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        self._backend.save(s)
        return s

    @contextmanager
    def trace(
        self,
        model: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> Generator[Span, None, None]:
        """Context-manager API: wall-clock timing is captured automatically.

        The yielded :class:`Span` is mutable; assign ``span.response`` (and
        any other fields) inside the block.  ``ended_at`` and
        ``duration_ms`` are set on exit, then the span is persisted to the
        configured backend.

        Example::

            with tracer.trace("gpt-4o", "What is the boiling point of water?") as span:
                span.response = call_llm(span.prompt)
        """
        if not model:
            raise ValueError("model must be a non-empty string")
        if prompt is None:
            raise ValueError("prompt must not be None")
        started = datetime.now(timezone.utc)
        s = Span(
            id=str(uuid.uuid4()),
            model=model,
            prompt=prompt,
            response="",
            started_at=started.isoformat(),
            ended_at="",
            duration_ms=0.0,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        try:
            yield s
        finally:
            ended = datetime.now(timezone.utc)
            s.ended_at = ended.isoformat()
            s.duration_ms = round((ended - started).total_seconds() * 1000, 3)
            self._backend.save(s)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def spans(self) -> List[Span]:
        """Return all recorded spans in insertion order."""
        return self._backend.load_all()  # type: ignore[return-value]

    def filter(
        self,
        model: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        has_parent: Optional[bool] = None,
    ) -> List[Span]:
        """Return spans matching all supplied criteria.

        Parameters
        ----------
        model:
            Exact model name to match.
        min_duration_ms:
            Inclusive lower bound on ``duration_ms``.
        has_parent:
            ``True`` to keep only child spans; ``False`` for root spans only.
        """
        result: List[Span] = self._backend.load_all()  # type: ignore[assignment]
        if model is not None:
            result = [s for s in result if s.model == model]
        if min_duration_ms is not None:
            result = [s for s in result if s.duration_ms >= min_duration_ms]
        if has_parent is not None:
            result = [s for s in result if (s.parent_id is not None) == has_parent]
        return result

    def export(self) -> List[Dict[str, Any]]:
        """Export all spans as a list of JSON-serialisable dicts."""
        return [s.to_dict() for s in self._backend.load_all()]  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def cost_estimate(self, price_per_1k_tokens: float = 0.002) -> float:
        """Rough cost estimate based on approximate token count.

        Tokens are approximated as ``(characters / 4)``, a common rule of
        thumb for English text.  Adjust *price_per_1k_tokens* to match
        your provider's rate card.
        """
        total_tokens = sum(
            s.token_estimate for s in self._backend.load_all()  # type: ignore[union-attr]
        )
        return round((total_tokens / 1000) * price_per_1k_tokens, 6)

    def summary(self) -> Dict[str, Any]:
        """Aggregate statistics across all recorded spans."""
        spans: List[Span] = self._backend.load_all()  # type: ignore[assignment]
        if not spans:
            return {"count": 0, "total_duration_ms": 0.0, "models": {}}
        models: Dict[str, int] = {}
        for s in spans:
            models[s.model] = models.get(s.model, 0) + 1
        total_ms = sum(s.duration_ms for s in spans)
        return {
            "count": len(spans),
            "total_duration_ms": total_ms,
            "avg_duration_ms": round(total_ms / len(spans), 2),
            "models": models,
            "cost_estimate": self.cost_estimate(),
        }

    def clear(self) -> None:
        """Clear all recorded spans from the backend."""
        self._backend.clear()
