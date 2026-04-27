# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-27

### Added
- `TraceContext` class and `Llmtrace.trace()` context-manager API: wraps an
  LLM call and records accurate `started_at`, `ended_at`, and `duration_ms`
  automatically using `time.monotonic()`.
- `Llmtrace.save_json(path)` / `load_json(path)` — persist and restore spans
  as a JSON file (stdlib `json`; zero new dependencies).
- `Llmtrace.save_sqlite(path)` / `load_sqlite(path)` — persist and restore
  spans in a SQLite database (stdlib `sqlite3`; upsert semantics on re-save).
- `src/llmtrace/gui.py` — interactive Tkinter viewer (`llmtrace-gui` CLI
  entry point) supporting load/save, column-sort, filter controls, and a
  full prompt/response detail pane.
- `llmtrace-gui` console script registered in `pyproject.toml`.
- Input validation on `Llmtrace.span()`: raises `ValueError` for non-string
  or empty `model`; raises `TypeError` for non-string `prompt`/`response`.
- `TraceContext` exported from the top-level `llmtrace` package.

### Changed
- Version bumped from 0.1.0 to 0.2.0.
- `Llmtrace.filter()` now initialises `result` as a copy of `self._spans`
  rather than a reference, making the filtering chain consistent.

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- `Llmtrace.span()` for manual span recording with model, prompt, response,
  duration, metadata, and parent-id fields.
- `filter()`, `export()`, `summary()`, `cost_estimate()`, and `clear()`.
- Comprehensive pytest test suite (13 tests).
