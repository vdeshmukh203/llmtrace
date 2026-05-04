---
title: 'llmtrace: lightweight tracing for large language model API calls'
tags:
  - Python
  - large language models
  - observability
  - tracing
  - reproducibility
authors:
  - name: Vaibhav Deshmukh
    affiliation: 1
affiliations:
  - name: Independent Researcher
    index: 1
date: 25 April 2026
bibliography: paper.bib
---

# Summary

`llmtrace` is a Python library for collecting structured *spans* from large
language model (LLM) [@brown2020language] API calls.  Each span records the
model name, prompt, response, wall-clock duration, and an approximate token
count, producing a uniform record of activity across providers.  Spans are
stored in a pluggable backend — an in-memory list (default), a JSON-lines
file, or a SQLite database — so they can be inspected, compared, or replayed
without standing up additional infrastructure.  A context-manager interface
captures timing automatically, and a self-contained browser dashboard
visualises the collected spans in real time.

# Statement of need

Engineers and researchers building on LLMs routinely need to inspect what was
sent to which model, how long it took, and what came back.
General-purpose distributed-tracing stacks such as OpenTelemetry require
integration work that is often disproportionate to small projects, prototypes,
or reproducibility experiments.  `llmtrace` targets that gap with a minimal,
dependency-light alternative: a context manager that captures spans locally
and exposes them for offline analysis.  This makes it well suited to academic
experiments where reproducibility and post-hoc inspection are essential, and
to early-stage development where heavyweight observability tooling adds more
friction than value.

The context-manager API records wall-clock timing automatically:

```python
from llmtrace import Llmtrace

tracer = Llmtrace()
with tracer.trace("gpt-4o", "Summarise the abstract") as span:
    span.response = call_llm(span.prompt)

print(tracer.summary())
```

Persistent storage requires only one extra line:

```python
from llmtrace import Llmtrace
from llmtrace.backends import JSONBackend, SQLiteBackend

tracer = Llmtrace(backend=JSONBackend("spans.jsonl"))
# or: Llmtrace(backend=SQLiteBackend("spans.db"))
```

A local web dashboard can be launched with:

```python
from llmtrace.gui import launch_dashboard
launch_dashboard(tracer)  # opens http://localhost:8765
```

# Design

`llmtrace` follows three design principles.

**Zero external dependencies.**  The library uses only the Python standard
library (`dataclasses`, `sqlite3`, `http.server`, `contextlib`), which
eliminates version-conflict friction common in research environments and makes
installation reliable across operating systems.

**Pluggable storage.**  An abstract `Backend` base class defines a three-method
interface (`save`, `load_all`, `clear`).  `MemoryBackend` (default) stores
spans in a Python list.  `JSONBackend` appends each span as a JSON object on
its own line (JSON-lines format) so the file is valid even if the process is
interrupted.  `SQLiteBackend` persists spans in a local SQLite database, which
supports concurrent readers and large span collections.  Custom backends can be
added by subclassing `Backend`.

**Automatic timing via a context manager.**  The `trace()` context manager
records `started_at` at entry and `ended_at` plus `duration_ms` at exit,
ensuring timing is always consistent with the actual call duration.  The
`span()` method is provided for post-hoc recording when the caller already
holds timing information.

# Acknowledgements

This work was developed independently.  The author thanks the open-source
community whose tooling made this project possible.

# References
