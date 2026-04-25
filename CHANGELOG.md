# Changelog

All notable changes to llmtrace are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-25

### Added
- Initial release of llmtrace.
- Context-manager API for wrapping LLM API calls with a span.
- Captures model, prompt, response, duration, and cost on each span.
- Pluggable JSON and SQLite storage back ends.
