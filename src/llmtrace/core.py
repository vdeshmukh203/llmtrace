"""LLM call tracer with timing, filtering, and export."""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional


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

    def __repr__(self) -> str:
        return (
            f"Span(id={self.id[:8]}…, model={self.model!r}, "
            f"duration_ms={self.duration_ms:.1f})"
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

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Span":
        return cls(
            id=d["id"],
            model=d["model"],
            prompt=d["prompt"],
            response=d["response"],
            started_at=d["started_at"],
            ended_at=d["ended_at"],
            duration_ms=float(d["duration_ms"]),
            metadata=d.get("metadata") or {},
            parent_id=d.get("parent_id"),
        )


class _TraceContext:
    """Mutable context yielded by :meth:`Llmtrace.trace`."""

    def __init__(self, span: Span) -> None:
        self._span = span
        self.response: str = ""

    @property
    def id(self) -> str:
        return self._span.id


class Llmtrace:
    """LLM call tracer."""

    def __init__(self) -> None:
        self._spans: List[Span] = []

    # ------------------------------------------------------------------ #
    # Recording                                                            #
    # ------------------------------------------------------------------ #

    def span(
        self,
        model: str,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        parent_id: Optional[str] = None,
    ) -> Span:
        """Record a completed LLM span."""
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

    @contextmanager
    def trace(
        self,
        model: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> Generator[_TraceContext, None, None]:
        """Context manager that times the block and records a span on exit.

        Example::

            with tracer.trace("gpt-4o", prompt) as ctx:
                ctx.response = call_llm(prompt)
        """
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        s = Span(
            id=str(uuid.uuid4()),
            model=model,
            prompt=prompt,
            response="",
            started_at=started_at,
            ended_at=started_at,
            duration_ms=0.0,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        ctx = _TraceContext(s)
        try:
            yield ctx
        finally:
            s.response = ctx.response
            s.ended_at = datetime.now(timezone.utc).isoformat()
            s.duration_ms = round((time.perf_counter() - t0) * 1000, 3)
            self._spans.append(s)

    # ------------------------------------------------------------------ #
    # Querying                                                             #
    # ------------------------------------------------------------------ #

    def spans(self) -> List[Span]:
        """Return all recorded spans."""
        return list(self._spans)

    def filter(
        self,
        model: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        has_parent: Optional[bool] = None,
    ) -> List[Span]:
        """Filter spans by model, duration, or parent relationship."""
        result = self._spans
        if model is not None:
            result = [s for s in result if s.model == model]
        if min_duration_ms is not None:
            result = [s for s in result if s.duration_ms >= min_duration_ms]
        if has_parent is not None:
            result = [s for s in result if (s.parent_id is not None) == has_parent]
        return list(result)

    # ------------------------------------------------------------------ #
    # Export / import                                                      #
    # ------------------------------------------------------------------ #

    def export(self) -> List[Dict[str, Any]]:
        """Export all spans as a list of dicts (JSON-serialisable)."""
        return [s.to_dict() for s in self._spans]

    def save_json(self, path: str) -> None:
        """Persist all spans to a JSON file."""
        import json
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.export(), fh, indent=2)

    def load_json(self, path: str) -> None:
        """Append spans loaded from a JSON file."""
        import json
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for d in data:
            self._spans.append(Span.from_dict(d))

    def save_sqlite(self, path: str) -> None:
        """Persist all spans to a SQLite database."""
        import json
        import sqlite3
        con = sqlite3.connect(path)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS spans (
                id TEXT PRIMARY KEY,
                model TEXT,
                prompt TEXT,
                response TEXT,
                started_at TEXT,
                ended_at TEXT,
                duration_ms REAL,
                metadata TEXT,
                parent_id TEXT
            )
            """
        )
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
        con.close()

    def load_sqlite(self, path: str) -> None:
        """Append spans loaded from a SQLite database."""
        import json
        import sqlite3
        con = sqlite3.connect(path)
        rows = con.execute(
            "SELECT id,model,prompt,response,started_at,ended_at,"
            "duration_ms,metadata,parent_id FROM spans"
        ).fetchall()
        con.close()
        for row in rows:
            self._spans.append(
                Span(
                    id=row[0], model=row[1], prompt=row[2], response=row[3],
                    started_at=row[4], ended_at=row[5], duration_ms=row[6],
                    metadata=json.loads(row[7]) if row[7] else {},
                    parent_id=row[8],
                )
            )

    # ------------------------------------------------------------------ #
    # Analytics                                                            #
    # ------------------------------------------------------------------ #

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
