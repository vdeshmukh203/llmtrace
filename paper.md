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
model name, prompt, response, wall-clock duration, and an estimated cost,
producing a uniform record of activity across providers.  Spans can be queried
and filtered in-memory, serialised to JSON files for offline analysis, and
inspected interactively through a built-in Tkinter dashboard.

# Statement of need

Engineers and researchers building on LLMs routinely need to inspect what was
sent to which model, how long it took, and what came back.  General-purpose
distributed-tracing stacks such as OpenTelemetry [@opentelemetry2023] require
significant integration work that is often disproportionate to small projects,
prototypes, or reproducibility experiments.  Managed observability platforms
(LangSmith, Weights & Biases, etc.) add external service dependencies and
authentication overhead.

`llmtrace` targets that gap with a minimal, zero-dependency alternative: a
Python API that captures spans locally in process and exposes them for
immediate inspection or offline analysis.  This makes it well suited to:

- **Academic experiments** where reproducibility requires a self-contained
  record of every model call.
- **Early-stage development** where heavyweight observability tooling adds
  more friction than value.
- **Multi-provider benchmarks** where a single tracer should work uniformly
  across OpenAI, Anthropic, and other vendors.

# Design and features

`llmtrace` provides two recording interfaces.  The `span()` method accepts a
completed call's metadata after the fact:

```python
tracer.span("gpt-4o", prompt=p, response=r, duration_ms=340)
```

The `trace()` context manager wraps live calls and measures duration
automatically:

```python
with tracer.trace("gpt-4o", prompt=p) as ctx:
    ctx.response = openai_client.complete(p)
```

Spans carry an optional `parent_id` field so that nested call graphs (e.g.
a summarisation step followed by a translation step) can be linked.

Recorded spans can be queried with `filter()` (by model name, minimum
duration, and parent status), aggregated with `summary()`, and serialised
to or from JSON files via `save_json()` / `load_json()`.

An interactive Tkinter dashboard (`python -m llmtrace`) allows practitioners
to browse spans in a sortable table, inspect full prompt and response text,
apply filters, and export results — all without standing up external
infrastructure.

Input validation raises `ValueError` with descriptive messages on invalid
arguments (empty model name, negative duration, negative cost rate), and the
context manager stores exception information in span metadata so that failed
calls are still traceable.

# Acknowledgements

This work was developed independently.  The author thanks the open-source
community whose tooling made this project possible.

# References
