"""Tkinter-based GUI dashboard for llmtrace.

Launch standalone::

    python -m llmtrace.gui

Or attach to an existing tracer::

    from llmtrace import Llmtrace
    from llmtrace.gui import launch
    tracer = Llmtrace()
    ...
    launch(tracer)
"""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from .backends import JsonBackend
from .core import Llmtrace, Span


class LlmtraceGUI:
    """Interactive dashboard for inspecting, filtering, and exporting spans."""

    def __init__(self, tracer: Optional[Llmtrace] = None) -> None:
        self._tracer = tracer or Llmtrace()
        self._root = tk.Tk()
        self._root.title("llmtrace Dashboard")
        self._root.geometry("1050x720")
        self._root.minsize(700, 500)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(2, weight=1)

        self._build_summary_bar()
        self._build_toolbar()
        self._build_filter_bar()
        self._build_table()
        self._build_detail_panel()

        self._refresh()

    def _build_summary_bar(self) -> None:
        bar = ttk.Frame(self._root, padding=(10, 6))
        bar.grid(row=0, column=0, sticky="ew")
        self._stats_var = tk.StringVar(value="No spans recorded.")
        ttk.Label(bar, textvariable=self._stats_var, font=("TkDefaultFont", 11, "bold")).pack(
            side=tk.LEFT
        )

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self._root, padding=(10, 2))
        bar.grid(row=1, column=0, sticky="ew")
        for label, cmd in [
            ("Load JSON", self._load_json),
            ("Save JSON", self._save_json),
            ("Load SQLite", self._load_sqlite),
            ("Save SQLite", self._save_sqlite),
            ("Clear", self._clear),
            ("Refresh", self._refresh),
        ]:
            ttk.Button(bar, text=label, command=cmd).pack(side=tk.LEFT, padx=3)

    def _build_filter_bar(self) -> None:
        frame = ttk.LabelFrame(self._root, text="Filters", padding=(8, 4))
        frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))

        ttk.Label(frame, text="Model:").pack(side=tk.LEFT)
        self._model_var = tk.StringVar()
        self._model_combo = ttk.Combobox(
            frame, textvariable=self._model_var, width=22, state="readonly"
        )
        self._model_combo.pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(frame, text="Min duration (ms):").pack(side=tk.LEFT)
        self._min_dur_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._min_dur_var, width=9).pack(side=tk.LEFT, padx=4)

        ttk.Button(frame, text="Apply", command=self._apply_filter).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(frame, text="Reset", command=self._reset_filter).pack(side=tk.LEFT)

    def _build_table(self) -> None:
        frame = ttk.Frame(self._root, padding=(8, 4))
        frame.grid(row=3, column=0, sticky="nsew", padx=0, pady=0)
        self._root.rowconfigure(3, weight=1)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        cols = ("model", "duration_ms", "prompt", "response", "started_at", "parent")
        headers = {
            "model": "Model",
            "duration_ms": "Duration (ms)",
            "prompt": "Prompt",
            "response": "Response",
            "started_at": "Started At",
            "parent": "Parent",
        }
        widths = {
            "model": 130,
            "duration_ms": 110,
            "prompt": 220,
            "response": 220,
            "started_at": 175,
            "parent": 90,
        }

        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for col in cols:
            self._tree.heading(
                col, text=headers[col], command=lambda c=col: self._sort_by(c)
            )
            self._tree.column(col, width=widths[col], minwidth=60, stretch=(col == "prompt"))

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        # Alternate row colours
        self._tree.tag_configure("odd", background="#f5f5f5")

    def _build_detail_panel(self) -> None:
        frame = ttk.LabelFrame(self._root, text="Span Details", padding=(8, 4))
        frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 6))
        frame.columnconfigure(0, weight=1)

        self._detail_text = tk.Text(
            frame, height=7, wrap=tk.WORD, state=tk.DISABLED,
            font=("TkFixedFont", 10), relief=tk.FLAT,
        )
        sb = ttk.Scrollbar(frame, orient="vertical", command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=sb.set)
        self._detail_text.grid(row=0, column=0, sticky="ew")
        sb.grid(row=0, column=1, sticky="ns")

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Re-populate the table and update the model dropdown."""
        models = sorted({s.model for s in self._tracer.spans()})
        current = self._model_var.get()
        self._model_combo["values"] = [""] + models
        if current not in models:
            self._model_var.set("")
        self._apply_filter()

    def _update_stats(self, spans: List[Span]) -> None:
        total = self._tracer.summary()
        if total["count"] == 0:
            self._stats_var.set("No spans recorded.")
            return
        self._stats_var.set(
            f"Showing {len(spans)} of {total['count']} spans  |  "
            f"Avg: {total['avg_duration_ms']} ms  |  "
            f"Total: {total['total_duration_ms']:.1f} ms  |  "
            f"Est. cost: ${total['cost_estimate']:.6f}"
        )

    def _populate_table(self, spans: List[Span]) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)
        for idx, sp in enumerate(spans):
            tag = "odd" if idx % 2 else ""
            self._tree.insert(
                "", tk.END, iid=sp.id,
                tags=(tag,),
                values=(
                    sp.model,
                    f"{sp.duration_ms:.1f}",
                    _truncate(sp.prompt, 70),
                    _truncate(sp.response, 70),
                    sp.started_at[:19].replace("T", " "),
                    sp.parent_id[:8] + "…" if sp.parent_id else "—",
                ),
            )

    # ------------------------------------------------------------------
    # Filter / sort
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        model = self._model_var.get().strip() or None
        min_dur_str = self._min_dur_var.get().strip()
        try:
            min_dur: Optional[float] = float(min_dur_str) if min_dur_str else None
        except ValueError:
            messagebox.showerror("Invalid filter", "Min duration must be a number.")
            return
        spans = self._tracer.filter(model=model, min_duration_ms=min_dur)
        self._populate_table(spans)
        self._update_stats(spans)

    def _reset_filter(self) -> None:
        self._model_var.set("")
        self._min_dur_var.set("")
        self._apply_filter()

    def _sort_by(self, col: str) -> None:
        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        try:
            items.sort(key=lambda x: float(x[0]))
        except ValueError:
            items.sort(key=lambda x: x[0].lower())
        for i, (_, k) in enumerate(items):
            self._tree.move(k, "", i)
            tag = "odd" if i % 2 else ""
            self._tree.item(k, tags=(tag,))

    # ------------------------------------------------------------------
    # Span detail
    # ------------------------------------------------------------------

    def _on_select(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        sel = self._tree.selection()
        if not sel:
            return
        span_id = sel[0]
        span = next((s for s in self._tracer.spans() if s.id == span_id), None)
        if span is None:
            return
        detail = (
            f"ID:       {span.id}\n"
            f"Model:    {span.model}\n"
            f"Started:  {span.started_at}\n"
            f"Ended:    {span.ended_at}\n"
            f"Duration: {span.duration_ms} ms\n"
            f"Parent:   {span.parent_id or '—'}\n"
            f"Metadata: {span.metadata}\n"
            f"\nPrompt\n{'─' * 60}\n{span.prompt}\n"
            f"\nResponse\n{'─' * 60}\n{span.response}"
        )
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert("1.0", detail)
        self._detail_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_json(self) -> None:
        path = filedialog.askopenfilename(
            title="Load JSON spans",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.load_json(path)
            self._refresh()
            messagebox.showinfo("Loaded", f"Spans loaded from:\n{path}")
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _save_json(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save JSON spans",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.save_json(path)
            messagebox.showinfo("Saved", f"Spans saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def _load_sqlite(self) -> None:
        path = filedialog.askopenfilename(
            title="Load SQLite database",
            filetypes=[("SQLite files", "*.db *.sqlite *.sqlite3"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.load_sqlite(path)
            self._refresh()
            messagebox.showinfo("Loaded", f"Spans loaded from:\n{path}")
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _save_sqlite(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save SQLite database",
            defaultextension=".db",
            filetypes=[("SQLite files", "*.db *.sqlite"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._tracer.save_sqlite(path)
            messagebox.showinfo("Saved", f"Spans saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def _clear(self) -> None:
        if messagebox.askyesno("Clear spans", "Remove all recorded spans?"):
            self._tracer.clear()
            self._refresh()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the Tk event loop (blocks until the window is closed)."""
        self._root.mainloop()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] + "…" if len(text) > max_len else text


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def launch(tracer: Optional[Llmtrace] = None) -> None:
    """Open the llmtrace dashboard window.

    Args:
        tracer: An existing :class:`~llmtrace.Llmtrace` instance whose spans
            will be pre-loaded into the dashboard.  A new empty tracer is
            created when *None* is passed.
    """
    LlmtraceGUI(tracer=tracer).run()


if __name__ == "__main__":  # python -m llmtrace.gui
    launch()
