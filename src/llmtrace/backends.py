"""Pluggable storage backends for llmtrace spans."""
import json
import sqlite3
from typing import List

from .core import Span


class JsonBackend:
    """Persist and load spans as a JSON file."""

    def __init__(self, path: str) -> None:
        self.path = path

    def save(self, spans: List[Span]) -> None:
        """Write *spans* to ``self.path``, overwriting any existing file."""
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump([s.to_dict() for s in spans], fh, indent=2)

    def load(self) -> List[Span]:
        """Read spans from ``self.path`` and return them as a list."""
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        return [Span(**d) for d in data]


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spans (
    id          TEXT PRIMARY KEY,
    model       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    parent_id   TEXT
)
"""

_INSERT = """
INSERT OR REPLACE INTO spans
    (id, model, prompt, response, started_at, ended_at, duration_ms, metadata, parent_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteBackend:
    """Persist and load spans in a SQLite database."""

    def __init__(self, path: str) -> None:
        self.path = path
        with sqlite3.connect(self.path) as conn:
            conn.execute(_CREATE_TABLE)

    def save(self, spans: List[Span]) -> None:
        """Upsert *spans* into the database (existing IDs are replaced)."""
        rows = [
            (
                s.id, s.model, s.prompt, s.response,
                s.started_at, s.ended_at, s.duration_ms,
                json.dumps(s.metadata), s.parent_id,
            )
            for s in spans
        ]
        with sqlite3.connect(self.path) as conn:
            conn.executemany(_INSERT, rows)

    def load(self) -> List[Span]:
        """Read all spans from the database ordered by ``started_at``."""
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT id, model, prompt, response, started_at, ended_at, "
                "duration_ms, metadata, parent_id FROM spans ORDER BY started_at"
            ).fetchall()
        return [
            Span(
                id=r[0], model=r[1], prompt=r[2], response=r[3],
                started_at=r[4], ended_at=r[5], duration_ms=r[6],
                metadata=json.loads(r[7] or "{}"), parent_id=r[8],
            )
            for r in rows
        ]
