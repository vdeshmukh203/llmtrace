# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-04

### Added
- `Llmtrace.trace()` context-manager API: wall-clock timing captured automatically.
- `backends` module with abstract `Backend` base class, `MemoryBackend` (default),
  `JSONBackend` (JSON-lines file), and `SQLiteBackend`.
- `Span.token_estimate` property: approximate token count via the 4-chars-per-token
  rule of thumb.
- `Span.from_dict()` classmethod for deserialising stored spans.
- `gui` module: `launch_dashboard()` starts a local web dashboard (auto-refreshes
  every 5 s) using only the Python standard library.
- Input validation: `ValueError` is raised for an empty model name or `None` prompt.

### Changed
- `cost_estimate()` now uses `price_per_1k_tokens` (previously `price_per_1k_chars`)
  and estimates tokens as `characters / 4`.
- `Llmtrace.__init__()` accepts an optional `backend` parameter.
- `__version__` bumped to `0.2.0`.

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- `Llmtrace.span()` for recording completed LLM call spans.
- Span fields: model, prompt, response, timestamps, duration, metadata, parent_id.
- `filter()`, `export()`, `summary()`, `cost_estimate()`, `clear()`.
