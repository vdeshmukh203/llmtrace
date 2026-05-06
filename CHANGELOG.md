# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-06

### Added
- `Llmtrace.trace()` context manager: wraps an LLM call block, measures
  wall-clock duration with `time.perf_counter`, and records a span on exit
  (including on exception).
- `Llmtrace.save_json()` / `load_json()`: persist and restore spans as a
  JSON file.
- `Llmtrace.save_sqlite()` / `load_sqlite()`: persist and restore spans in a
  SQLite database (`INSERT OR REPLACE` semantics so re-saving is safe).
- `Span.from_dict()` class method for round-trip deserialisation.
- `Span.__repr__` for readable inspection in REPLs and debuggers.
- `llmtrace.gui` module with `launch_viewer()`: a zero-extra-dependency
  Tkinter span viewer with model/duration filtering, sortable columns, full
  span detail pane, and File menu for opening/saving JSON and SQLite files.
- `llmtrace-viewer` CLI entry point that opens the GUI viewer.

### Fixed
- `started_at` and `ended_at` are now distinct when using the `trace()`
  context manager (previously both were set to the same timestamp).

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- `Llmtrace.span()` for recording completed LLM calls.
- `Llmtrace.filter()` for querying by model, duration, and parent relationship.
- `Llmtrace.export()` for JSON-serialisable span export.
- `Llmtrace.summary()` and `Llmtrace.cost_estimate()` for aggregate analytics.
- `Llmtrace.clear()` to reset the tracer.
