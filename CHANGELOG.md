# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-07

### Added
- `Llmtrace.trace()` context manager that measures wall-clock duration with
  `time.perf_counter` and records a span automatically on exit, even when an
  exception is raised.
- `JsonBackend` — reads and writes spans to a JSON file.
- `SQLiteBackend` — reads and writes spans to a SQLite database using
  `INSERT OR REPLACE` (idempotent upserts).
- `Llmtrace.save_json()`, `load_json()`, `save_sqlite()`, `load_sqlite()`
  convenience methods that delegate to the backends above.
- `llmtrace.gui` module: a `tkinter` dashboard (`LlmtraceGUI`) with a
  filterable/sortable span table, detail pane, summary bar, and load/save
  buttons for JSON and SQLite files.  Launch with `python -m llmtrace.gui`
  or via `llmtrace.gui.launch(tracer)`.
- `__repr__` on `Span` for easier interactive inspection.
- `JsonBackend` and `SQLiteBackend` are now exported from the top-level
  `llmtrace` package.

### Fixed
- `Llmtrace.span()` previously set both `started_at` and `ended_at` to the
  same timestamp.  `started_at` is now computed as `ended_at − duration_ms`,
  so the two fields are always consistent.

### Changed
- Version bumped to 0.2.0.
- `pyproject.toml`: added `keywords` and `classifiers`; corrected version.
- `paper.md`: updated to describe the context manager, backends, and GUI that
  are now implemented; added OpenTelemetry citation.

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- `Llmtrace.span()` for recording completed LLM API calls with model, prompt,
  response, duration, and optional metadata and parent ID.
- `Llmtrace.filter()`, `export()`, `summary()`, `cost_estimate()`, `clear()`.
