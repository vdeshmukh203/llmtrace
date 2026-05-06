"""Lightweight LLM call tracing and span collection."""
__version__ = "0.2.0"
from .core import Llmtrace, Span
from .gui import launch_viewer
__all__ = ["Llmtrace", "Span", "launch_viewer"]
