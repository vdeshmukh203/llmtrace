# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-09

### Added
- **Context-manager API** (`Llmtrace.trace`): records wall-clock `started_at`,
  `ended_at`, and `duration_ms` automatically; span is committed on block exit
  even when an exception is raised.
- **`JsonBackend`**: persists spans to a UTF-8 JSON file with atomic writes
  (write-to-temp-then-rename).
- **`SqliteBackend`**: persists spans to a SQLite database; supports
  `":memory:"` for in-process use; upserts on duplicate span `id`.
- **`Dashboard` (web GUI)**: zero-dependency browser UI served by Python's
  built-in `http.server`; shows summary statistics, a timeline bar chart, a
  filterable/sortable span table, and a JSON export button; auto-refreshes
  every 5 seconds.
- Thread safety: `Llmtrace` and `SqliteBackend` now serialise all mutations
  with `threading.Lock`.
- Input validation: `Llmtrace.span` and `Llmtrace.trace` raise `ValueError` /
  `TypeError` on invalid arguments (empty model, wrong types, negative
  duration).
- `JsonBackend`, `SqliteBackend`, and `__version__` exported from the top-level
  `llmtrace` package.

### Fixed
- `Span.started_at` and `Span.ended_at` were previously identical (both
  captured at recording time rather than at call start and end).  The
  context-manager API now captures these correctly; the manual `span()` method
  documents that both fields reflect the moment of recording when no timing
  data is supplied.

### Changed
- Version bumped from 0.1.0 → 0.2.0.
- `Llmtrace.__init__` accepts an optional `backend` keyword argument.
- `Llmtrace.clear()` clears in-memory spans only; backend data is unaffected.

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- `Llmtrace.span()`: record a completed LLM call with model, prompt, response,
  duration, and metadata.
- `Llmtrace.filter()`, `export()`, `cost_estimate()`, `summary()`, `clear()`.
- `Span.to_dict()` for JSON serialisation.
