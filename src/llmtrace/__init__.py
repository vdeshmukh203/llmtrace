"""Lightweight LLM call tracing and span collection."""
__version__ = "0.2.0"
from .core import Llmtrace, Span
__all__ = ["Llmtrace", "Span", "__version__"]
