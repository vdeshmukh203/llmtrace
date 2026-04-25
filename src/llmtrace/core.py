"""LLM call tracer."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid


@dataclass
class Span:
    id: str
    model: str
    prompt: str
    response: str
    started_at: str
    ended_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class Llmtrace:
    """LLM call tracer."""
    def __init__(self): self._spans: List[Span] = []
    def span(self, model, prompt, response, metadata=None):
        now = datetime.now(timezone.utc).isoformat()
        s = Span(str(uuid.uuid4()), model, prompt, response, now, now, metadata or {})
        self._spans.append(s); return s
    def spans(self): return list(self._spans)
    def clear(self): self._spans.clear()
