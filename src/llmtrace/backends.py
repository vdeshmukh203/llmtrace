"""Pluggable storage backends for llmtrace.

Two built-in backends are provided:

* :class:`JsonBackend` — stores spans in a single JSON file.
* :class:`SqliteBackend` — stores spans in a SQLite database.

Both implement the same three-method contract required by
:class:`~llmtrace.core.Llmtrace`:

* ``append(span: Span) -> None``
* ``load() -> List[Span]``
* ``save(spans: List[Span]) -> None``

Custom backends must implement the same interface.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Protocol, runtime_checkable

from .core import Span


@runtime_checkable
class _Backend(Protocol):
    """Structural type for llmtrace storage backends."""

    def append(self, span: Span) -> None: ...

    def load(self) -> List[Span]: ...

    def save(self, spans: List[Span]) -> None: ...


def _span_from_dict(d: Dict[str, Any]) -> Span:
    return Span(
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


class JsonBackend:
    """Persist spans to a UTF-8 JSON file.

    The file is written atomically via a temporary file so a crash during
    :meth:`append` or :meth:`save` cannot corrupt existing data.

    Parameters
    ----------
    path:
        File-system path for the JSON file.  Created (with an empty span
        list) if it does not exist.

    Examples
    --------
    ::

        from llmtrace import Llmtrace
        from llmtrace.backends import JsonBackend

        tracer = Llmtrace(backend=JsonBackend("spans.json"))
        with tracer.trace("gpt-4o", prompt="Hello") as ctx:
            ctx.response = "Hi!"
    """

    def __init__(self, path: str) -> None:
        self.path = path

    # ------------------------------------------------------------------
    # Backend protocol
    # ------------------------------------------------------------------

    def append(self, span: Span) -> None:
        """Append *span* to the JSON file (creates the file if absent)."""
        existing = self.load() if os.path.exists(self.path) else []
        existing.append(span)
        self._write(existing)

    def load(self) -> List[Span]:
        """Return all spans stored in the JSON file.

        Raises
        ------
        FileNotFoundError
            If the file does not yet exist.
        """
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        return [_span_from_dict(d) for d in data]

    def save(self, spans: List[Span]) -> None:
        """Overwrite the JSON file with *spans* (pass ``[]`` to clear)."""
        self._write(spans)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write(self, spans: List[Span]) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([s.to_dict() for s in spans], fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)


class SqliteBackend:
    """Persist spans to a SQLite database.

    The ``spans`` table is created automatically on first use.  The backend
    uses ``INSERT OR REPLACE`` so re-inserting a span with the same ``id``
    is idempotent.

    Parameters
    ----------
    path:
        File-system path for the SQLite database.  Pass ``":memory:"`` for
        a transient in-process database (useful in tests).

    Examples
    --------
    ::

        from llmtrace import Llmtrace
        from llmtrace.backends import SqliteBackend

        tracer = Llmtrace(backend=SqliteBackend("runs.db"))
        with tracer.trace("claude-3-5-sonnet", prompt="Hello") as ctx:
            ctx.response = "Hi!"
    """

    _CREATE = (
        "CREATE TABLE IF NOT EXISTS spans ("
        "id TEXT PRIMARY KEY, model TEXT NOT NULL, "
        "prompt TEXT NOT NULL, response TEXT NOT NULL, "
        "started_at TEXT NOT NULL, ended_at TEXT NOT NULL, "
        "duration_ms REAL NOT NULL, metadata TEXT, parent_id TEXT)"
    )
    _INSERT = (
        "INSERT OR REPLACE INTO spans "
        "(id, model, prompt, response, started_at, ended_at, "
        "duration_ms, metadata, parent_id) VALUES (?,?,?,?,?,?,?,?,?)"
    )
    _SELECT_ALL = "SELECT id, model, prompt, response, started_at, ended_at, duration_ms, metadata, parent_id FROM spans ORDER BY started_at"
    _DELETE_ALL = "DELETE FROM spans"

    def __init__(self, path: str) -> None:
        self.path = path
        # Keep a single persistent connection so ":memory:" databases survive
        # across method calls.  check_same_thread=False is safe here because
        # all access is serialised by _lock.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(self._CREATE)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Backend protocol
    # ------------------------------------------------------------------

    def append(self, span: Span) -> None:
        """Insert *span* into the database (idempotent on duplicate ``id``)."""
        with self._lock:
            self._conn.execute(self._INSERT, self._row(span))
            self._conn.commit()

    def load(self) -> List[Span]:
        """Return all spans in chronological order."""
        with self._lock:
            rows = self._conn.execute(self._SELECT_ALL).fetchall()
        return [self._span(row) for row in rows]

    def save(self, spans: List[Span]) -> None:
        """Replace all rows with *spans* (pass ``[]`` to clear the table)."""
        with self._lock:
            self._conn.execute(self._DELETE_ALL)
            self._conn.executemany(self._INSERT, [self._row(s) for s in spans])
            self._conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row(span: Span):
        return (
            span.id, span.model, span.prompt, span.response,
            span.started_at, span.ended_at, span.duration_ms,
            json.dumps(span.metadata, ensure_ascii=False),
            span.parent_id,
        )

    @staticmethod
    def _span(row) -> Span:
        return Span(
            id=row[0], model=row[1], prompt=row[2], response=row[3],
            started_at=row[4], ended_at=row[5], duration_ms=row[6],
            metadata=json.loads(row[7]) if row[7] else {},
            parent_id=row[8],
        )
