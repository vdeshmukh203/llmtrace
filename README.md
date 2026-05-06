# llmtrace

Lightweight LLM call tracing and span collection.

`llmtrace` records structured spans from large language model API calls — capturing
the model, prompt, response, wall-clock duration, and estimated cost — with no
external dependencies and no additional infrastructure required.

## Installation

```
pip install llmtrace
```

## Quick start

### Context manager (recommended)

Use `tracer.trace()` to time a block automatically and record a span on exit:

```python
from llmtrace import Llmtrace

tracer = Llmtrace()

with tracer.trace("gpt-4o", "What is the capital of France?") as ctx:
    # call your LLM here; set ctx.response before the block exits
    ctx.response = "Paris"

print(tracer.summary())
# {'count': 1, 'total_duration_ms': 0.123, 'avg_duration_ms': 0.12, ...}
```

### Manual span recording

For already-completed calls where you know the duration:

```python
tracer.span("claude-3-5-sonnet", prompt, response, duration_ms=412.7)
```

### Filtering

```python
slow = tracer.filter(min_duration_ms=500)
gpt_calls = tracer.filter(model="gpt-4o")
children = tracer.filter(has_parent=True)
```

### Persistence

```python
# JSON
tracer.save_json("spans.json")

tracer2 = Llmtrace()
tracer2.load_json("spans.json")

# SQLite
tracer.save_sqlite("spans.db")

tracer3 = Llmtrace()
tracer3.load_sqlite("spans.db")
```

### Export to dict

```python
import json
print(json.dumps(tracer.export(), indent=2))
```

### Cost estimate

```python
# Character-based approximation (provider-agnostic)
print(tracer.cost_estimate(price_per_1k_chars=0.002))
```

## GUI viewer

A built-in Tkinter viewer lets you browse, filter, and inspect spans interactively.

```python
from llmtrace import launch_viewer
launch_viewer(tracer)      # pass an existing Llmtrace instance
```

Or launch it from the command line after recording spans to a file:

```
llmtrace-viewer
```

The viewer supports opening/saving JSON and SQLite files from the **File** menu,
filtering by model or minimum duration, sortable columns, and full span detail on selection.

> **Note:** Tkinter must be available (`apt install python3-tk` on Debian/Ubuntu).

## License

MIT
