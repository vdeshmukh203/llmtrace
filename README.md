# llmtrace

[![CI](https://github.com/vdeshmukh203/llmtrace/actions/workflows/ci.yml/badge.svg)](https://github.com/vdeshmukh203/llmtrace/actions)
[![PyPI](https://img.shields.io/pypi/v/llmtrace)](https://pypi.org/project/llmtrace/)
[![Python](https://img.shields.io/pypi/pyversions/llmtrace)](https://pypi.org/project/llmtrace/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Lightweight LLM call tracing and span collection for Python.**

`llmtrace` records structured *spans* from large language model API calls—model name, prompt, response, wall-clock duration, and cost estimate—with zero external dependencies and a minimal API designed for academic experiments, prototypes, and reproducibility workflows.

---

## Features

- **Context-manager API** — automatic wall-clock timing with `with tracer.trace(...)`.
- **Manual recording** — `tracer.span(...)` for replaying or importing existing records.
- **Persistent storage** — plug in `JsonBackend` or `SqliteBackend`; custom backends via a three-method protocol.
- **Filtering & analytics** — filter by model, duration, or parent relationship; summary statistics and cost estimates.
- **Web dashboard** — one-line `Dashboard(tracer).open().serve_forever()` launches a browser UI (zero external dependencies, served by Python's built-in `http.server`).
- **Thread-safe** — all tracer and backend operations are protected by a `threading.Lock`.
- **Zero dependencies** — standard library only (Python ≥ 3.8).

---

## Installation

```bash
pip install llmtrace
```

---

## Quick start

### Automatic timing (recommended)

```python
from llmtrace import Llmtrace

tracer = Llmtrace()

with tracer.trace("gpt-4o", prompt="Explain entropy in one sentence") as ctx:
    # replace the line below with your actual LLM call
    ctx.response = "Entropy measures the number of microscopic configurations..."
    ctx.metadata["tokens"] = 42          # enrich metadata inside the block

print(ctx.span.duration_ms)             # wall-clock ms
print(tracer.summary())
```

### Manual span recording

```python
s = tracer.span(
    model="claude-3-5-sonnet",
    prompt="Translate 'hello' to French.",
    response="Bonjour.",
    duration_ms=310.0,
    metadata={"temperature": 0.7},
)
```

### Persistent storage

```python
from llmtrace import Llmtrace, JsonBackend, SqliteBackend

# JSON file — human-readable, easy to share
tracer = Llmtrace(backend=JsonBackend("spans.json"))

# SQLite — faster for large numbers of spans
tracer = Llmtrace(backend=SqliteBackend("runs.db"))

# Spans are persisted on every call; a new Llmtrace with the same backend
# automatically loads existing spans on construction.
tracer2 = Llmtrace(backend=SqliteBackend("runs.db"))
print(len(tracer2.spans()))    # same spans as tracer
```

### Web dashboard

```python
from llmtrace.gui import Dashboard

dash = Dashboard(tracer)
dash.open()           # starts server and opens a browser tab
dash.serve_forever()  # blocks; Ctrl-C to stop
```

The dashboard auto-refreshes every 5 seconds and provides:

- Summary statistics (span count, total/average duration, per-model counts, cost estimate)
- Timeline bar chart
- Filterable, sortable span table with full prompt/response inspection
- One-click JSON export

---

## API reference

### `Llmtrace(backend=None)`

| Method | Description |
|---|---|
| `trace(model, prompt="", metadata=None, parent_id=None)` | Context manager; records a timed span on exit. |
| `span(model, prompt, response, duration_ms=0.0, metadata=None, parent_id=None)` | Record a completed span with explicit timing. |
| `spans()` | Snapshot list of all recorded spans. |
| `filter(model=None, min_duration_ms=None, has_parent=None)` | Filter spans (AND semantics). |
| `export()` | All spans as a list of JSON-serialisable dicts. |
| `cost_estimate(price_per_1k_chars=0.002)` | Rough cost estimate in USD. |
| `summary()` | Aggregate statistics dict. |
| `clear()` | Remove all in-memory spans. |

### `Span` fields

| Field | Type | Description |
|---|---|---|
| `id` | `str` | UUID v4 |
| `model` | `str` | Model identifier |
| `prompt` | `str` | Input text |
| `response` | `str` | Output text |
| `started_at` | `str` | ISO 8601 UTC timestamp |
| `ended_at` | `str` | ISO 8601 UTC timestamp |
| `duration_ms` | `float` | Wall-clock latency (ms) |
| `metadata` | `dict` | Caller-supplied key/value pairs |
| `parent_id` | `str \| None` | Parent span ID for nested traces |

### `JsonBackend(path)` / `SqliteBackend(path)`

Both implement `append(span)`, `load() → List[Span]`, and `save(spans)`.

Pass `":memory:"` to `SqliteBackend` for an in-process database (useful in tests).

### `Dashboard(tracer, host="127.0.0.1", port=5173)`

| Method | Description |
|---|---|
| `start()` | Start HTTP server in a background daemon thread; returns `self`. |
| `open()` | Start server (if needed) and open a browser tab; returns `self`. |
| `serve_forever()` | Block until Ctrl-C. |
| `shutdown()` | Stop the server. |
| `url` | Base URL, e.g. `http://127.0.0.1:5173`. |

---

## Hierarchical tracing

```python
with tracer.trace("orchestrator-model", prompt="Plan a trip") as root:
    root.response = plan_response

with tracer.trace("detail-model", parent_id=root.span.id) as child:
    child.response = detail_response

root_spans  = tracer.filter(has_parent=False)
child_spans = tracer.filter(has_parent=True)
```

---

## Contributing

Bug reports and pull requests are welcome on GitHub.  
Please run the test suite before submitting:

```bash
pip install -e .
pytest tests/ -v
```

---

## Citation

If you use `llmtrace` in published research, please cite:

```bibtex
@software{deshmukh2026llmtrace,
  author  = {Deshmukh, Vaibhav},
  title   = {llmtrace: lightweight tracing for large language model API calls},
  year    = {2026},
  url     = {https://github.com/vdeshmukh203/llmtrace},
}
```

## License

MIT © Vaibhav Deshmukh
