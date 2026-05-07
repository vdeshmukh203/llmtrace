# llmtrace

Lightweight LLM call tracing and span collection for Python.

`llmtrace` records structured *spans* from LLM API calls—model name, prompt,
response, wall-clock timing, and estimated cost—without requiring any external
infrastructure.  Spans can be filtered and analysed in memory, persisted to
JSON or SQLite, and inspected in an interactive GUI dashboard.

## Installation

```bash
pip install llmtrace
```

No third-party dependencies; only the Python standard library is required.

## Quick start

### Record a completed call

```python
from llmtrace import Llmtrace

tracer = Llmtrace()

# Record a call you have already timed yourself
span = tracer.span(
    model="gpt-4o",
    prompt="What is the capital of France?",
    response="Paris",
    duration_ms=312.4,
)
print(span)
# Span(id=a1b2c3d4…, model='gpt-4o', duration_ms=312.4)
```

### Time a call with the context manager

```python
import openai  # example; any client works

client = openai.OpenAI()

with tracer.trace("gpt-4o", prompt) as ctx:
    reply = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    ctx["response"] = reply.choices[0].message.content
```

The span is recorded automatically when the `with` block exits, even if an
exception is raised.

### Analyse recorded spans

```python
# Summary statistics
print(tracer.summary())
# {'count': 5, 'total_duration_ms': 1842.3, 'avg_duration_ms': 368.46,
#  'models': {'gpt-4o': 3, 'claude-3': 2}, 'cost_estimate': 0.000123}

# Filter by model or minimum duration
slow = tracer.filter(model="gpt-4o", min_duration_ms=500)

# Export to a JSON-serialisable list
data = tracer.export()
```

### Persist and reload

```python
# JSON
tracer.save_json("spans.json")

tracer2 = Llmtrace()
tracer2.load_json("spans.json")

# SQLite
tracer.save_sqlite("spans.db")

tracer2 = Llmtrace()
tracer2.load_sqlite("spans.db")
```

Backends can also be used directly:

```python
from llmtrace import JsonBackend, SQLiteBackend

JsonBackend("spans.json").save(tracer.spans())
spans = JsonBackend("spans.json").load()
```

### GUI dashboard

```python
from llmtrace.gui import launch

launch(tracer)          # opens dashboard pre-loaded with tracer's spans
launch()                # opens empty dashboard; load JSON/SQLite via menus
```

Or from the command line:

```bash
python -m llmtrace.gui
```

The dashboard shows a filterable, sortable table of spans with timing and cost
information, a detail pane for the selected span, and buttons to load or save
JSON and SQLite files.

## API reference

### `Llmtrace`

| Method | Description |
|--------|-------------|
| `span(model, prompt, response, *, metadata, duration_ms, parent_id)` | Record a completed span. |
| `trace(model, prompt, *, metadata, parent_id)` | Context manager that times the wrapped block. |
| `spans()` | Return all recorded spans. |
| `filter(model, min_duration_ms, has_parent)` | Return spans matching all supplied predicates. |
| `export()` | Return all spans as a JSON-serialisable list of dicts. |
| `summary()` | Aggregate statistics (count, duration, model breakdown, cost). |
| `cost_estimate(price_per_1k_chars)` | Rough cost proxy based on character count. |
| `save_json(path)` / `load_json(path)` | Persist/reload spans as JSON. |
| `save_sqlite(path)` / `load_sqlite(path)` | Persist/reload spans in SQLite. |
| `clear()` | Remove all recorded spans. |

### `Span` fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID for this span. |
| `model` | `str` | Model identifier (e.g. `"gpt-4o"`). |
| `prompt` | `str` | Input text sent to the model. |
| `response` | `str` | Text returned by the model. |
| `started_at` | `str` | ISO 8601 UTC timestamp when the call started. |
| `ended_at` | `str` | ISO 8601 UTC timestamp when the call ended. |
| `duration_ms` | `float` | Wall-clock duration in milliseconds. |
| `metadata` | `dict` | Arbitrary caller-supplied key/value pairs. |
| `parent_id` | `str \| None` | ID of a parent span for nested calls. |

### Backends

| Class | Description |
|-------|-------------|
| `JsonBackend(path)` | Read/write a JSON file containing a list of span dicts. |
| `SQLiteBackend(path)` | Read/write a SQLite database with an `INSERT OR REPLACE` upsert strategy. |

## License

MIT
