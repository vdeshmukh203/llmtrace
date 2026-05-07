---
title: 'llmtrace: lightweight tracing for large language model API calls'
tags:
  - Python
  - large language models
  - observability
  - tracing
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
producing a uniform record of activity across providers.  Spans are recorded
either by passing timing information explicitly or through a context manager
that measures elapsed time automatically.  Recorded spans can be filtered and
summarised in memory, persisted to JSON files or a SQLite database for offline
analysis, and inspected in an interactive GUI dashboard.

# Statement of need

Engineers and researchers building on LLMs routinely need to inspect what was
sent to which model, how long it took, and what came back.  General-purpose
distributed-tracing stacks such as OpenTelemetry [@opentelemetry2023] require
significant integration work that is often disproportionate to the needs of
small projects, prototypes, or reproducibility experiments.  `llmtrace` targets
that gap with a minimal, dependency-light alternative: a tracer object that
captures spans locally using only the Python standard library and exposes them
for offline analysis through a simple API and a graphical dashboard.

The library is well suited to academic experiments where reproducibility and
post-hoc inspection are essential, and to early-stage development where
heavyweight observability tooling adds more friction than value.

# Design and implementation

`llmtrace` exposes two span-recording primitives.  `Llmtrace.span()` records a
call that has already completed, inferring `started_at` from `ended_at` minus
the supplied `duration_ms`.  `Llmtrace.trace()` is a context manager that
records `started_at` on entry and computes `duration_ms` using
`time.perf_counter` on exit, capturing the response from a caller-supplied dict.
Spans are stored in an in-memory list from which they can be queried with
`filter()`, summarised with `summary()`, and exported with `export()`.

Persistence is provided by two pluggable backends.  `JsonBackend` serialises
spans to a JSON file.  `SQLiteBackend` writes to a SQLite database using
`INSERT OR REPLACE` so that repeated saves are idempotent.  Both backends are
accessible directly or through convenience methods (`save_json`, `load_json`,
`save_sqlite`, `load_sqlite`) on the `Llmtrace` object.

An interactive dashboard (`llmtrace.gui`) built with the standard-library
`tkinter` toolkit allows researchers to load span files, filter and sort the
span table, inspect individual span details, and save results, without writing
any additional code.

# Acknowledgements

This work was developed independently.  The author thanks the open-source
community whose tooling made this project possible.

# References
