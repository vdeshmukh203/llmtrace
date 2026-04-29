# llmtrace

Lightweight tracing and span collection for Large Language Model (LLM) API calls.

[![CI](https://github.com/vdeshmukh203/llmtrace/actions/workflows/ci.yml/badge.svg)](https://github.com/vdeshmukh203/llmtrace/actions)
[![PyPI](https://img.shields.io/pypi/v/llmtrace)](https://pypi.org/project/llmtrace/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

`llmtrace` captures structured *spans* from LLM API calls — recording the model
name, prompt, response, wall-clock duration, and estimated cost — without
requiring any external infrastructure.  It is designed for:

- **Academic experiments** where reproducibility and post-hoc inspection matter.
- **Early-stage development** where heavyweight observability stacks add
  friction.
- **Offline analysis** of prompt/response pairs across multiple providers.

## Installation

```
pip install llmtrace
```

Python ≥ 3.8, zero external dependencies.

## Quick start

```python
from llmtrace import Llmtrace

tracer = Llmtrace()

# Option A – record a completed call directly
tracer.span("gpt-4o", prompt="What is 2+2?", response="4", duration_ms=340)

# Option B – wrap a live call with the context manager
with tracer.trace("gpt-4o", prompt="What is 2+2?") as ctx:
    ctx.response = call_my_llm("What is 2+2?")  # your API call here

# Inspect results
print(tracer.summary())
# {'count': 2, 'total_duration_ms': ..., 'avg_duration_ms': ...,
#  'models': {'gpt-4o': 2}, 'cost_estimate': ...}
```

## API reference

### `Llmtrace`

| Method | Description |
|---|---|
| `span(model, prompt, response, *, metadata, duration_ms, parent_id)` | Record a completed call; returns a `Span`. |
| `trace(model, prompt, *, metadata, parent_id)` | Context manager; set `ctx.response` inside the block. |
| `spans()` | Return all recorded spans (insertion order). |
| `filter(*, model, min_duration_ms, has_parent)` | Return spans matching all supplied criteria. |
| `summary()` | Aggregate statistics: count, durations, model breakdown, cost. |
| `cost_estimate(price_per_1k_chars=0.002)` | Rough USD cost from character counts. |
| `export()` | All spans as a list of JSON-serialisable dicts. |
| `save_json(path)` | Write spans to a JSON file. |
| `load_json(path)` | Append spans from a JSON file created by `save_json`. |
| `clear()` | Remove all recorded spans. |

### `Span` fields

`id`, `model`, `prompt`, `response`, `started_at`, `ended_at`,
`duration_ms`, `metadata`, `parent_id`.

`Span.to_dict()` / `Span.from_dict(d)` provide serialisation round-trips.

## Dashboard GUI

A Tkinter dashboard is included:

```
# Launch from the command line
python -m llmtrace

# Or embed in your own script
from llmtrace import Llmtrace
from llmtrace.gui import launch_gui

tracer = Llmtrace()
# … record spans …
launch_gui(tracer)
```

The dashboard lets you:

- Browse spans in a sortable table.
- Filter by model, minimum duration, and parent relationship.
- Inspect full prompt/response text in the detail pane.
- Export to JSON or load a previously saved file.

## Nested call graphs

```python
parent = tracer.span("gpt-4o", "Summarise the following …", summary)
tracer.span("gpt-4o", "Translate the summary …", translation,
            parent_id=parent.id)
```

## Persistence

```python
tracer.save_json("session.json")

# Later, in another script
new_tracer = Llmtrace()
new_tracer.load_json("session.json")
```

## Running the tests

```
pip install pytest
pytest
```

## Contributing

Bug reports and pull requests are welcome on
[GitHub](https://github.com/vdeshmukh203/llmtrace/issues).

## License

[MIT](LICENSE) © Vaibhav Deshmukh
