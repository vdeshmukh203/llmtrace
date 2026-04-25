"""LLM call tracer with timing, filtering, and export."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class Span:
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
        return {
            "id": self.id, "model": self.model,
            "prompt": self.prompt, "response": self.response,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "duration_ms": self.duration_ms, "metadata": self.metadata,
            "parent_id": self.parent_id,
        }


class Llmtrace:
    """LLM call tracer."""

    def __init__(self):
        self._spans: List[Span] = []

    def span(self, model: str, prompt: str, response: str,
             metadata: Optional[Dict[str, Any]] = None,
             duration_ms: float = 0.0,
             parent_id: Optional[str] = None) -> Span:
        """Record a completed LLM span."""
        now = datetime.now(timezone.utc).isoformat()
        s = Span(id=str(uuid.uuid4()), model=model, prompt=prompt,
                 response=response, started_at=now, ended_at=now,
                 duration_ms=duration_ms, metadata=metadata or {},
                 parent_id=parent_id)
        self._spans.append(s)
        return s

    def spans(self) -> List[Span]:
        """Return all recorded spans."""
        return list(self._spans)

    def filter(self, model: Optional[str] = None,
               min_duration_ms: Optional[float] = None,
               has_parent: Optional[bool] = None) -> List[Span]:
        """Filter spans by model, duration, or parent relationship."""
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
        """Rough cost estimate based on prompt+response character count."""
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
            "total_duration_ms": total_ms,
            "avg_duration_ms": round(total_ms / len(self._spans), 2),
            "models": models,
            "cost_estimate": self.cost_estimate(),
        }

    def clear(self) -> None:
        """Clear all recorded spans."""
        self._spans.clear()
