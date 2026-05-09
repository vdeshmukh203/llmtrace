"""Lightweight LLM call tracing and span collection.

Quick start::

    from llmtrace import Llmtrace

    tracer = Llmtrace()

    # Automatic timing via context manager
    with tracer.trace("gpt-4o", prompt="Hello") as ctx:
        ctx.response = "Hi!"          # replace with your actual LLM call
    print(ctx.span.duration_ms)

    # Manual span recording
    s = tracer.span("gpt-4o", prompt="Hi", response="Hello", duration_ms=310)

    # Inspect
    print(tracer.summary())

    # Persistent storage
    from llmtrace.backends import JsonBackend
    tracer2 = Llmtrace(backend=JsonBackend("spans.json"))

    # Web dashboard
    from llmtrace.gui import Dashboard
    Dashboard(tracer).open().serve_forever()
"""
__version__ = "0.2.0"

from .backends import JsonBackend, SqliteBackend
from .core import Llmtrace, Span

__all__ = ["Llmtrace", "Span", "JsonBackend", "SqliteBackend", "__version__"]
