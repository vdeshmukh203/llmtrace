# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-29

### Added
- `Llmtrace.trace()` context manager that wraps live LLM calls, measures
  wall-clock duration automatically, and stores exception information in span
  metadata when the block raises.
- `Llmtrace.save_json(path)` and `Llmtrace.load_json(path)` for JSON-file
  persistence (replaces the previously documented but unimplemented backend).
- `Span.from_dict()` classmethod for deserialisation round-trips.
- `Span.__repr__` and `Llmtrace.__repr__` for easier debugging.
- Built-in Tkinter dashboard (`python -m llmtrace` / `llmtrace-gui`) with
  sortable span table, detail pane, filter controls, and JSON export/load.
- Input validation: `ValueError` on empty model name, negative `duration_ms`,
  and negative `price_per_1k_chars`.
- `summary()` now includes `avg_duration_ms` and `cost_estimate` even when
  the span list is empty (consistent schema in all cases).
- PyPI classifiers, `keywords`, and `[project.urls]` in `pyproject.toml`.
- `llmtrace-gui` console-script entry point.

### Fixed
- `started_at` and `ended_at` were both set to the same timestamp when
  recording a completed span; `started_at` is now correctly computed as
  `ended_at − duration_ms`.
- Metadata dict passed to `span()` is now copied defensively so that
  subsequent mutations of the caller's dict do not affect the stored span.

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- `Llmtrace.span()` for recording completed LLM calls.
- `filter()`, `export()`, `cost_estimate()`, `summary()`, and `clear()`.
