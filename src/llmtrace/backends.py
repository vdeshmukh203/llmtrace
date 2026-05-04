"""Pluggable storage backends for llmtrace spans."""
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union


class Backend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def save(self, span: object) -> None: ...

    @abstractmethod
    def load_all(self) -> List[object]: ...

    @abstractmethod
    def clear(self) -> None: ...


class MemoryBackend(Backend):
    """In-process list storage (default, zero I/O overhead)."""

    def __init__(self) -> None:
        self._spans: List[object] = []

    def save(self, span: object) -> None:
        self._spans.append(span)

    def load_all(self) -> List[object]:
        return list(self._spans)

    def clear(self) -> None:
        self._spans.clear()


class JSONBackend(Backend):
    """Append-only JSON-lines file storage.

    Each span is written as a single JSON object on its own line so the
    file remains valid even if the process is interrupted mid-write.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)

    def save(self, span: object) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(span.to_dict()) + "\n")  # type: ignore[attr-defined]

    def load_all(self) -> List[object]:
        from .core import Span  # deferred to break import cycle

        if not self._path.exists():
            return []
        spans = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    spans.append(Span.from_dict(json.loads(line)))
        return spans

    def clear(self) -> None:
        if self._path.exists():
            self._path.write_text("", encoding="utf-8")


class SQLiteBackend(Backend):
    """SQLite storage backend.

    Spans are stored in a single ``spans`` table and retrieved ordered by
    ``started_at`` so the call sequence is preserved across restarts.
    """

    _CREATE = (
        "CREATE TABLE IF NOT EXISTS spans ("
        "id TEXT PRIMARY KEY,"
        "model TEXT NOT NULL,"
        "prompt TEXT NOT NULL,"
        "response TEXT NOT NULL,"
        "started_at TEXT NOT NULL,"
        "ended_at TEXT NOT NULL,"
        "duration_ms REAL NOT NULL,"
        "metadata TEXT NOT NULL DEFAULT '{}',"
        "parent_id TEXT"
        ")"
    )

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = str(path)
        con = sqlite3.connect(self._path)
        with con:
            con.execute(self._CREATE)
        con.close()

    def save(self, span: object) -> None:
        from .core import Span  # type: ignore[attr-defined]

        s = span  # type: ignore[assignment]
        con = sqlite3.connect(self._path)
        with con:
            con.execute(
                "INSERT OR REPLACE INTO spans"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    s.id, s.model, s.prompt, s.response,
                    s.started_at, s.ended_at, s.duration_ms,
                    json.dumps(s.metadata), s.parent_id,
                ),
            )
        con.close()

    def load_all(self) -> List[object]:
        from .core import Span  # deferred to break import cycle

        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM spans ORDER BY started_at"
        ).fetchall()
        con.close()
        return [
            Span(
                id=r["id"],
                model=r["model"],
                prompt=r["prompt"],
                response=r["response"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                duration_ms=r["duration_ms"],
                metadata=json.loads(r["metadata"]),
                parent_id=r["parent_id"],
            )
            for r in rows
        ]

    def clear(self) -> None:
        con = sqlite3.connect(self._path)
        with con:
            con.execute("DELETE FROM spans")
        con.close()
