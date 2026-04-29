"""LLM call tracer with timing, filtering, and export."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """A single recorded LLM call."""

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

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Span":
        """Reconstruct a Span from a dict produced by :meth:`to_dict`."""
        return cls(
            id=d["id"],
            model=d["model"],
            prompt=d["prompt"],
            response=d["response"],
            started_at=d["started_at"],
            ended_at=d["ended_at"],
            duration_ms=float(d["duration_ms"]),
            metadata=dict(d.get("metadata") or {}),
            parent_id=d.get("parent_id"),
        )

    def __repr__(self) -> str:
        return (
            f"Span(id={self.id[:8]}…, model={self.model!r}, "
            f"duration_ms={self.duration_ms})"
        )


class _SpanContext:
    """Context manager returned by :meth:`Llmtrace.trace`.

    Set ``ctx.response`` inside the ``with`` block; the completed span is
    available as ``ctx.span`` after the block exits.

    Example::

        with tracer.trace("gpt-4o", prompt) as ctx:
            ctx.response = call_llm(prompt)
        print(ctx.span.duration_ms)
    """

    def __init__(
        self,
        tracer: "Llmtrace",
        model: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]],
        parent_id: Optional[str],
    ) -> None:
        self._tracer = tracer
        self._model = model
        self._prompt = prompt
        self._metadata: Dict[str, Any] = dict(metadata or {})
        self._parent_id = parent_id
        self._started_at: Optional[datetime] = None
        self.response: str = ""
        self.span: Optional[Span] = None

    def __enter__(self) -> "_SpanContext":
        self._started_at = datetime.now(timezone.utc)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ended_at = datetime.now(timezone.utc)
        assert self._started_at is not None
        duration_ms = (ended_at - self._started_at).total_seconds() * 1000
        if exc_type is not None:
            self._metadata.setdefault("error", f"{exc_type.__name__}: {exc_val}")
        self.span = Span(
            id=str(uuid.uuid4()),
            model=self._model,
            prompt=self._prompt,
            response=self.response,
            started_at=self._started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_ms=round(duration_ms, 3),
            metadata=self._metadata,
            parent_id=self._parent_id,
        )
        self._tracer._spans.append(self.span)


class Llmtrace:
    """Lightweight in-process recorder for LLM API call spans.

    Example::

        tracer = Llmtrace()

        # Record a completed call directly
        tracer.span("gpt-4o", prompt="Hello", response="Hi!", duration_ms=340)

        # Or wrap a live call with the context manager
        with tracer.trace("gpt-4o", prompt) as ctx:
            ctx.response = call_llm(prompt)

        print(tracer.summary())
    """

    def __init__(self) -> None:
        self._spans: List[Span] = []

    # ── Recording ─────────────────────────────────────────────────────────

    def span(
        self,
        model: str,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        parent_id: Optional[str] = None,
    ) -> Span:
        """Record a completed LLM call and return the resulting :class:`Span`.

        Args:
            model: Model identifier (e.g. ``"gpt-4o"``).
            prompt: The prompt text sent to the model.
            response: The text returned by the model.
            metadata: Arbitrary key-value pairs to attach to the span.
            duration_ms: Wall-clock time of the call in milliseconds (≥ 0).
            parent_id: ID of a parent span for nested call graphs.

        Returns:
            The newly created and stored :class:`Span`.

        Raises:
            ValueError: If *model* is empty or *duration_ms* is negative.
        """
        if not model:
            raise ValueError("model must be a non-empty string")
        if duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")

        ended_at = datetime.now(timezone.utc)
        started_at = ended_at - timedelta(milliseconds=duration_ms)

        s = Span(
            id=str(uuid.uuid4()),
            model=model,
            prompt=prompt,
            response=response,
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_ms=duration_ms,
            metadata=dict(metadata or {}),
            parent_id=parent_id,
        )
        self._spans.append(s)
        return s

    def trace(
        self,
        model: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> _SpanContext:
        """Return a context manager that records a live LLM call as a span.

        Args:
            model: Model identifier.
            prompt: The prompt that will be sent.
            metadata: Arbitrary key-value pairs to attach.
            parent_id: ID of a parent span for nested call graphs.

        Returns:
            A :class:`_SpanContext`; set ``ctx.response`` inside the block.

        Raises:
            ValueError: If *model* is empty.
        """
        if not model:
            raise ValueError("model must be a non-empty string")
        return _SpanContext(self, model, prompt, metadata, parent_id)

    # ── Querying ──────────────────────────────────────────────────────────

    def spans(self) -> List[Span]:
        """Return a shallow copy of all recorded spans in insertion order."""
        return list(self._spans)

    def filter(
        self,
        model: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        has_parent: Optional[bool] = None,
    ) -> List[Span]:
        """Return spans matching all supplied criteria.

        Args:
            model: Keep only spans whose ``model`` field equals this value.
            min_duration_ms: Keep only spans with ``duration_ms`` ≥ this value.
            has_parent: If ``True`` keep only child spans; if ``False`` keep
                only root spans; if ``None`` (default) keep all.

        Returns:
            Filtered list of :class:`Span` objects.
        """
        result: List[Span] = list(self._spans)
        if model is not None:
            result = [s for s in result if s.model == model]
        if min_duration_ms is not None:
            result = [s for s in result if s.duration_ms >= min_duration_ms]
        if has_parent is not None:
            result = [s for s in result if (s.parent_id is not None) == has_parent]
        return result

    # ── Aggregation ───────────────────────────────────────────────────────

    def cost_estimate(self, price_per_1k_chars: float = 0.002) -> float:
        """Estimate total cost based on prompt + response character counts.

        Args:
            price_per_1k_chars: Cost in USD per 1 000 characters (default 0.002).

        Returns:
            Estimated cost rounded to six decimal places.
        """
        if price_per_1k_chars < 0:
            raise ValueError("price_per_1k_chars must be non-negative")
        total = sum(len(s.prompt) + len(s.response) for s in self._spans)
        return round((total / 1000) * price_per_1k_chars, 6)

    def summary(self) -> Dict[str, Any]:
        """Return aggregate statistics across all recorded spans.

        Returns:
            A dict with keys ``count``, ``total_duration_ms``,
            ``avg_duration_ms``, ``models``, and ``cost_estimate``.
        """
        if not self._spans:
            return {
                "count": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "models": {},
                "cost_estimate": 0.0,
            }
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

    # ── Persistence ───────────────────────────────────────────────────────

    def export(self) -> List[Dict[str, Any]]:
        """Return all spans as a list of JSON-serialisable dicts."""
        return [s.to_dict() for s in self._spans]

    def save_json(self, path: str) -> None:
        """Write all spans to a JSON file at *path* (overwrites existing file).

        Args:
            path: Destination file path.
        """
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.export(), fh, indent=2)

    def load_json(self, path: str) -> None:
        """Append spans from a JSON file previously created by :meth:`save_json`.

        Args:
            path: Source file path.

        Raises:
            ValueError: If the file does not contain a JSON array.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON array in {path!r}")
        for d in data:
            self._spans.append(Span.from_dict(d))

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all recorded spans."""
        self._spans.clear()

    def __repr__(self) -> str:
        return f"Llmtrace(spans={len(self._spans)})"
