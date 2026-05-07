"""LLM call tracer with timing, filtering, export, and persistence."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional
import time
import uuid


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

    def __repr__(self) -> str:
        return (
            f"Span(id={self.id[:8]}…, model={self.model!r}, "
            f"duration_ms={self.duration_ms})"
        )

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


class Llmtrace:
    """Collector and analyser for LLM API call spans."""

    def __init__(self) -> None:
        self._spans: List[Span] = []

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

        ``started_at`` is inferred as ``ended_at - duration_ms`` so that the
        two timestamps are always consistent.
        """
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
            metadata=metadata or {},
            parent_id=parent_id,
        )
        self._spans.append(s)
        return s

    @contextmanager
    def trace(
        self,
        model: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> Generator[Dict[str, str], None, None]:
        """Context manager that times an LLM call and records it as a span.

        Usage::

            with tracer.trace("gpt-4o", prompt) as ctx:
                ctx["response"] = call_llm(prompt)
        """
        started_at = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        ctx: Dict[str, str] = {"response": ""}
        try:
            yield ctx
        finally:
            duration_ms = round((time.perf_counter() - t0) * 1000, 3)
            ended_at = datetime.now(timezone.utc)
            s = Span(
                id=str(uuid.uuid4()),
                model=model,
                prompt=prompt,
                response=ctx.get("response", ""),
                started_at=started_at.isoformat(),
                ended_at=ended_at.isoformat(),
                duration_ms=duration_ms,
                metadata=metadata or {},
                parent_id=parent_id,
            )
            self._spans.append(s)

    def spans(self) -> List[Span]:
        """Return all recorded spans."""
        return list(self._spans)

    def filter(
        self,
        model: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        has_parent: Optional[bool] = None,
    ) -> List[Span]:
        """Return spans matching all supplied predicates."""
        result = self._spans
        if model is not None:
            result = [s for s in result if s.model == model]
        if min_duration_ms is not None:
            result = [s for s in result if s.duration_ms >= min_duration_ms]
        if has_parent is not None:
            result = [s for s in result if (s.parent_id is not None) == has_parent]
        return list(result)

    def export(self) -> List[Dict[str, Any]]:
        """Export all spans as a list of dicts (JSON-serialisable)."""
        return [s.to_dict() for s in self._spans]

    def cost_estimate(self, price_per_1k_chars: float = 0.002) -> float:
        """Rough cost estimate based on prompt+response character count.

        Real API pricing is token-based; this is a proxy suitable for
        relative comparisons and early-stage budgeting.
        """
        total = sum(len(s.prompt) + len(s.response) for s in self._spans)
        return round((total / 1000) * price_per_1k_chars, 6)

    def summary(self) -> Dict[str, Any]:
        """Aggregate statistics across all recorded spans."""
        if not self._spans:
            return {"count": 0, "total_duration_ms": 0.0, "models": {}}
        models: Dict[str, int] = {}
        for s in self._spans:
            models[s.model] = models.get(s.model, 0) + 1
        total_ms = sum(s.duration_ms for s in self._spans)
        return {
            "count": len(self._spans),
            "total_duration_ms": round(total_ms, 3),
            "avg_duration_ms": round(total_ms / len(self._spans), 2),
            "models": models,
            "cost_estimate": self.cost_estimate(),
        }

    def save_json(self, path: str) -> None:
        """Persist all spans to a JSON file."""
        from .backends import JsonBackend
        JsonBackend(path).save(self._spans)

    def load_json(self, path: str) -> None:
        """Load spans from a JSON file, appending to any existing spans."""
        from .backends import JsonBackend
        self._spans.extend(JsonBackend(path).load())

    def save_sqlite(self, path: str) -> None:
        """Persist all spans to a SQLite database."""
        from .backends import SQLiteBackend
        SQLiteBackend(path).save(self._spans)

    def load_sqlite(self, path: str) -> None:
        """Load spans from a SQLite database, appending to any existing spans."""
        from .backends import SQLiteBackend
        self._spans.extend(SQLiteBackend(path).load())

    def clear(self) -> None:
        """Clear all recorded spans."""
        self._spans.clear()
