"""Interactive Tkinter viewer for llmtrace spans.

Launch from the command line::

    llmtrace-gui                    # empty viewer
    llmtrace-gui spans.json         # pre-load a JSON file
    llmtrace-gui spans.db           # pre-load a SQLite database

Or programmatically::

    from llmtrace.gui import SpanViewer
    viewer = SpanViewer(tracer)
    viewer.mainloop()
"""
from __future__ import annotations

import sys
from typing import List, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except ImportError:  # pragma: no cover
    raise SystemExit(
        "The llmtrace GUI requires Tkinter.\n"
        "Install it with:  sudo apt-get install python3-tk  (Debian/Ubuntu)\n"
        "                  brew install python-tk             (macOS/Homebrew)"
    )

from .core import Llmtrace, Span

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PRICE_PER_1K = 0.002  # default USD / 1 000 chars used for per-row cost display


def _short(uid: Optional[str], n: int = 8) -> str:
    return uid[:n] if uid else ""


def _per_span_cost(span: Span) -> float:
    return round((len(span.prompt) + len(span.response)) / 1000 * _PRICE_PER_1K, 6)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class SpanViewer(tk.Tk):
    """Top-level window for browsing, filtering, and exporting spans."""

    # ------------------------------------------------------------------ init

    def __init__(self, tracer: Optional[Llmtrace] = None) -> None:
        super().__init__()
        self.title("LLMtrace Viewer")
        self.geometry("1050x720")
        self.minsize(800, 520)

        self._tracer: Llmtrace = tracer or Llmtrace()
        self._active: List[Span] = []

        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        self._build_toolbar()
        self._build_filter_bar()
        self._build_table()
        self._build_detail_panel()
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(4, 4, 4, 0))
        bar.pack(fill=tk.X)

        ttk.Button(bar, text="Load JSON",   command=self._cmd_load_json).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Load SQLite", command=self._cmd_load_sqlite).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)
        ttk.Button(bar, text="Save JSON",   command=self._cmd_save_json).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Save SQLite", command=self._cmd_save_sqlite).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)
        ttk.Button(bar, text="Clear All",   command=self._cmd_clear).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Refresh",     command=self._refresh).pack(side=tk.RIGHT, padx=2)

    def _build_filter_bar(self) -> None:
        frm = ttk.LabelFrame(self, text="Filter", padding=(6, 4))
        frm.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(frm, text="Model:").pack(side=tk.LEFT)
        self._v_model = tk.StringVar(value="All")
        self._combo_model = ttk.Combobox(
            frm, textvariable=self._v_model, width=22, state="readonly"
        )
        self._combo_model.pack(side=tk.LEFT, padx=(2, 10))

        ttk.Label(frm, text="Min duration (ms):").pack(side=tk.LEFT)
        self._v_min_dur = tk.StringVar()
        ttk.Entry(frm, textvariable=self._v_min_dur, width=8).pack(side=tk.LEFT, padx=(2, 10))

        ttk.Label(frm, text="Has parent:").pack(side=tk.LEFT)
        self._v_has_parent = tk.StringVar(value="All")
        ttk.Combobox(
            frm, textvariable=self._v_has_parent,
            values=["All", "Yes", "No"], width=6, state="readonly",
        ).pack(side=tk.LEFT, padx=(2, 10))

        ttk.Button(frm, text="Apply",  command=self._cmd_apply_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(frm, text="Reset",  command=self._cmd_reset_filter).pack(side=tk.LEFT, padx=2)

    def _build_table(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=4)

        cols = ("id", "model", "duration_ms", "cost", "started_at", "parent_id")
        self._tree = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse")

        headings = {
            "id":          ("Span ID",        90),
            "model":       ("Model",          150),
            "duration_ms": ("Duration (ms)",  110),
            "cost":        ("Cost ($)",        90),
            "started_at":  ("Started At",     210),
            "parent_id":   ("Parent ID",       90),
        }
        for col, (text, width) in headings.items():
            self._tree.heading(col, text=text,
                               command=lambda c=col: self._sort_by(c))
            anchor = tk.E if col in ("duration_ms", "cost") else tk.W
            self._tree.column(col, width=width, minwidth=60, anchor=anchor)

        vsb = ttk.Scrollbar(frm, orient=tk.VERTICAL,   command=self._tree.yview)
        hsb = ttk.Scrollbar(frm, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT,  fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        self._tree.bind("<<TreeviewSelect>>", self._on_row_select)
        self._sort_col: Optional[str] = None
        self._sort_rev = False

    def _build_detail_panel(self) -> None:
        pane = ttk.LabelFrame(self, text="Span Detail", padding=(6, 4))
        pane.pack(fill=tk.BOTH, padx=4, pady=(0, 4))

        for side, label, attr in (
            (tk.LEFT,  "Prompt",   "_text_prompt"),
            (tk.RIGHT, "Response", "_text_response"),
        ):
            box = ttk.Frame(pane)
            box.pack(fill=tk.BOTH, expand=True, side=side, padx=(0 if side == tk.LEFT else 8, 0))
            ttk.Label(box, text=label + ":").pack(anchor=tk.W)
            widget = scrolledtext.ScrolledText(box, height=5, wrap=tk.WORD, state=tk.DISABLED)
            widget.pack(fill=tk.BOTH, expand=True)
            setattr(self, attr, widget)

    def _build_status_bar(self) -> None:
        self._v_status = tk.StringVar(value="Ready")
        ttk.Label(
            self, textvariable=self._v_status,
            relief=tk.SUNKEN, anchor=tk.W, padding=(4, 2),
        ).pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=(0, 4))

    # ----------------------------------------------------------------- commands

    def _cmd_load_json(self) -> None:
        path = filedialog.askopenfilename(
            title="Load JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.load_json(path)
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _cmd_load_sqlite(self) -> None:
        path = filedialog.askopenfilename(
            title="Load SQLite database",
            filetypes=[("SQLite databases", "*.db *.sqlite"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.load_sqlite(path)
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _cmd_save_json(self) -> None:
        if not self._tracer.spans():
            messagebox.showinfo("Save JSON", "No spans to save.")
            return
        path = filedialog.asksaveasfilename(
            title="Save JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.save_json(path)
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def _cmd_save_sqlite(self) -> None:
        if not self._tracer.spans():
            messagebox.showinfo("Save SQLite", "No spans to save.")
            return
        path = filedialog.asksaveasfilename(
            title="Save SQLite database",
            defaultextension=".db",
            filetypes=[("SQLite databases", "*.db"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.save_sqlite(path)
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def _cmd_clear(self) -> None:
        if not self._tracer.spans():
            return
        if messagebox.askyesno("Clear all spans", "Remove all recorded spans?"):
            self._tracer.clear()
            self._refresh()

    def _cmd_apply_filter(self) -> None:
        model: Optional[str] = self._v_model.get() or None
        if model == "All":
            model = None

        min_dur: Optional[float] = None
        raw = self._v_min_dur.get().strip()
        if raw:
            try:
                min_dur = float(raw)
            except ValueError:
                messagebox.showerror("Filter error", "Min duration must be a number.")
                return

        has_parent: Optional[bool] = None
        hp = self._v_has_parent.get()
        if hp == "Yes":
            has_parent = True
        elif hp == "No":
            has_parent = False

        self._active = self._tracer.filter(
            model=model, min_duration_ms=min_dur, has_parent=has_parent
        )
        self._populate_table(self._active)
        self._update_status(self._active)

    def _cmd_reset_filter(self) -> None:
        self._v_model.set("All")
        self._v_min_dur.set("")
        self._v_has_parent.set("All")
        self._refresh()

    # ----------------------------------------------------------------- events

    def _on_row_select(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        sel = self._tree.selection()
        if not sel:
            return
        try:
            span = self._active[int(sel[0])]
        except (ValueError, IndexError):
            return
        for widget, text in (
            (self._text_prompt,   span.prompt),
            (self._text_response, span.response),
        ):
            widget.config(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert(tk.END, text)
            widget.config(state=tk.DISABLED)

    def _sort_by(self, col: str) -> None:
        """Toggle ascending/descending sort on a column header click."""
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        def _key(s: Span) -> Any:  # type: ignore[return]
            return getattr(s, col, "")

        self._active.sort(key=_key, reverse=self._sort_rev)
        self._populate_table(self._active)

    # ----------------------------------------------------------------- helpers

    def _refresh(self) -> None:
        self._active = self._tracer.spans()
        self._update_model_combo()
        self._populate_table(self._active)
        self._update_status(self._active)

    def _update_model_combo(self) -> None:
        models = sorted({s.model for s in self._tracer.spans()})
        self._combo_model["values"] = ["All"] + models
        if self._v_model.get() not in ["All"] + models:
            self._v_model.set("All")

    def _populate_table(self, spans: List[Span]) -> None:
        self._tree.delete(*self._tree.get_children())
        for i, s in enumerate(spans):
            self._tree.insert(
                "", tk.END, iid=str(i),
                values=(
                    _short(s.id),
                    s.model,
                    f"{s.duration_ms:.1f}",
                    f"{_per_span_cost(s):.6f}",
                    s.started_at,
                    _short(s.parent_id),
                ),
            )

    def _update_status(self, spans: List[Span]) -> None:
        if not spans:
            self._v_status.set("No spans to display.")
            return
        total_ms = sum(s.duration_ms for s in spans)
        avg_ms = total_ms / len(spans)
        cost = sum(_per_span_cost(s) for s in spans)
        models = ", ".join(sorted({s.model for s in spans}))
        self._v_status.set(
            f"Spans: {len(spans)}  |  "
            f"Total: {total_ms:.1f} ms  |  Avg: {avg_ms:.1f} ms  |  "
            f"Est. cost: ${cost:.6f}  |  Models: {models}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Command-line entry point: ``llmtrace-gui [file]``."""
    tracer = Llmtrace()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        try:
            if path.endswith((".db", ".sqlite")):
                tracer.load_sqlite(path)
            else:
                tracer.load_json(path)
        except Exception as exc:
            print(f"Warning: could not load {path!r}: {exc}", file=sys.stderr)

    SpanViewer(tracer).mainloop()


if __name__ == "__main__":
    main()
