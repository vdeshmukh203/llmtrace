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

`llmtrace` is a Python library for collecting structured spans from large language model (LLM) [@brown2020language] API calls. Each span records the model name, prompt, response, wall-clock duration, and estimated cost, producing a uniform record of activity across providers. Spans are written to a pluggable backend (JSON files or SQLite) so they can be inspected, compared, or replayed without standing up additional infrastructure.

# Statement of need

Engineers and researchers building on LLMs routinely need to inspect what was sent to which model, how long it took, and what came back. General-purpose distributed-tracing stacks such as OpenTelemetry require integration work that is often disproportionate to small projects, prototypes, or reproducibility experiments. `llmtrace` targets that gap with a minimal, dependency-light alternative: a context manager that captures spans locally and exposes them for offline analysis. This makes it well suited to academic experiments where reproducibility and post-hoc inspection are essential, and to early-stage development where heavyweight observability tooling adds more friction than value.

# Acknowledgements

This work was developed independently. The author thanks the open-source community whose tooling made this project possible.

# References
