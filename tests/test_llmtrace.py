"""Tests for llmtrace."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llmtrace import Llmtrace

def test_basic():
    t = Llmtrace()
    s = t.span("gpt-4o", "hello", "hi")
    assert s.model == "gpt-4o"
    assert len(t.spans()) == 1
    t.clear(); assert len(t.spans()) == 0
    print("llmtrace OK")

if __name__ == "__main__":
    test_basic(); print("All tests passed."); sys.exit(0)
