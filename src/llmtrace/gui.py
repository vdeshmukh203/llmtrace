"""Tkinter-based dashboard for visualising llmtrace spans.

Launch as a standalone script::

    python -m llmtrace.gui

Or embed in your own application::

    from llmtrace import Llmtrace
    from llmtrace.gui import launch_gui

    tracer = Llmtrace()
    # … record spans …
    launch_gui(tracer)
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from .core import Llmtrace, Span

# Column definitions: (treeview id, heading label, pixel width, anchor)
_COLUMNS = [
    ("id_short",    "ID",            80,  "w"),
    ("model",       "Model",        130,  "w"),
    ("prompt_short","Prompt",       220,  "w"),
    ("duration_ms", "Duration (ms)", 100, "e"),
    ("cost",        "Cost ($)",      90,  "e"),
    ("started_at",  "Started At",   185,  "w"),
]

_PRICE_PER_1K = 0.002  # default USD per 1 000 chars


def _short_id(span_id: str) -> str:
    return span_id[:8] + "…"


def _span_cost(s: Span) -> float:
    return round((len(s.prompt) + len(s.response)) / 1000 * _PRICE_PER_1K, 6)


class LlmtraceGUI:
    """Tkinter dashboard bound to an :class:`~llmtrace.Llmtrace` instance."""

    def __init__(self, tracer: Llmtrace, root: Optional[tk.Tk] = None) -> None:
        self.tracer = tracer
        self.root = root if root is not None else tk.Tk()
        self.root.title("llmtrace Dashboard")
        self.root.geometry("1150x680")
        self.root.minsize(820, 500)
        self._sort_col: str = ""
        self._sort_rev: bool = False
        self._build_ui()
        self._refresh()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._build_toolbar(row=0)
        self._build_main(row=1)
        self._build_statusbar(row=2)

    def _build_toolbar(self, row: int) -> None:
        bar = ttk.Frame(self.root, padding=(6, 4))
        bar.grid(row=row, column=0, sticky="ew")

        # ── Filter controls ──
        ttk.Label(bar, text="Model:").pack(side="left")
        self._model_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self._model_var, width=14).pack(
            side="left", padx=(2, 10))

        ttk.Label(bar, text="Min duration (ms):").pack(side="left")
        self._min_dur_var = tk.StringVar(value="0")
        ttk.Entry(bar, textvariable=self._min_dur_var, width=8).pack(
            side="left", padx=(2, 10))

        self._only_root_var = tk.BooleanVar()
        self._only_child_var = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Root spans only",
                        variable=self._only_root_var,
                        command=self._on_root_toggle).pack(side="left")
        ttk.Checkbutton(bar, text="Child spans only",
                        variable=self._only_child_var,
                        command=self._on_child_toggle).pack(side="left", padx=(4, 10))

        ttk.Button(bar, text="Apply", command=self._refresh).pack(side="left")
        ttk.Button(bar, text="Reset", command=self._reset_filters).pack(
            side="left", padx=(4, 0))

        ttk.Separator(bar, orient="vertical").pack(
            side="left", fill="y", padx=10)

        # ── Action buttons ──
        ttk.Button(bar, text="Export JSON", command=self._export_json).pack(
            side="left")
        ttk.Button(bar, text="Load JSON", command=self._load_json).pack(
            side="left", padx=4)
        ttk.Button(bar, text="Clear All", command=self._clear_all).pack(
            side="left")
        ttk.Button(bar, text="⟳ Refresh", command=self._refresh).pack(
            side="right")

    def _build_main(self, row: int) -> None:
        paned = ttk.PanedWindow(self.root, orient="vertical")
        paned.grid(row=row, column=0, sticky="nsew", padx=6, pady=(0, 4))

        # ── Spans table ──
        table_frame = ttk.Frame(paned)
        paned.add(table_frame, weight=3)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        col_ids = [c[0] for c in _COLUMNS]
        self._tree = ttk.Treeview(
            table_frame, columns=col_ids, show="headings", selectmode="browse")

        for cid, label, width, anchor in _COLUMNS:
            self._tree.heading(
                cid, text=label, command=lambda c=cid: self._sort_by(c))
            self._tree.column(cid, width=width, anchor=anchor, stretch=False)

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                             command=self._tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal",
                             command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Detail pane ──
        detail_frame = ttk.LabelFrame(paned, text="Span Detail", padding=6)
        paned.add(detail_frame, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)

        self._detail_text = tk.Text(
            detail_frame, wrap="word", state="disabled",
            font=("Courier", 10), background="#f8f8f8", relief="flat")
        detail_vsb = ttk.Scrollbar(detail_frame, orient="vertical",
                                    command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=detail_vsb.set)
        self._detail_text.grid(row=0, column=0, sticky="nsew")
        detail_vsb.grid(row=0, column=1, sticky="ns")

    def _build_statusbar(self, row: int) -> None:
        bar = ttk.Frame(self.root, relief="sunken", padding=(6, 2))
        bar.grid(row=row, column=0, sticky="ew")
        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self._status_var,
                  font=("TkDefaultFont", 9)).pack(side="left")

    # ── Callbacks ─────────────────────────────────────────────────────────

    def _on_root_toggle(self) -> None:
        if self._only_root_var.get():
            self._only_child_var.set(False)

    def _on_child_toggle(self) -> None:
        if self._only_child_var.get():
            self._only_root_var.set(False)

    def _reset_filters(self) -> None:
        self._model_var.set("")
        self._min_dur_var.set("0")
        self._only_root_var.set(False)
        self._only_child_var.set(False)
        self._refresh()

    def _refresh(self) -> None:
        model = self._model_var.get().strip() or None

        try:
            min_dur_raw = float(self._min_dur_var.get())
            min_dur: Optional[float] = min_dur_raw if min_dur_raw > 0 else None
        except ValueError:
            min_dur = None

        has_parent: Optional[bool] = None
        if self._only_child_var.get():
            has_parent = True
        elif self._only_root_var.get():
            has_parent = False

        spans = self.tracer.filter(
            model=model, min_duration_ms=min_dur, has_parent=has_parent)
        self._populate(spans)
        self._update_status(spans)

    def _populate(self, spans: List[Span]) -> None:
        self._tree.delete(*self._tree.get_children())
        for s in spans:
            prompt_preview = s.prompt[:60] + "…" if len(s.prompt) > 60 else s.prompt
            self._tree.insert("", "end", iid=s.id, values=(
                _short_id(s.id),
                s.model,
                prompt_preview,
                f"{s.duration_ms:.1f}",
                f"{_span_cost(s):.6f}",
                s.started_at[:23].replace("T", " "),
            ))

    def _on_select(self, _event: object = None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        span_id = sel[0]
        span_map = {s.id: s for s in self.tracer.spans()}
        s = span_map.get(span_id)
        if s is None:
            return
        lines = [
            f"ID:          {s.id}",
            f"Model:       {s.model}",
            f"Started At:  {s.started_at}",
            f"Ended At:    {s.ended_at}",
            f"Duration:    {s.duration_ms} ms",
            f"Cost est.:   ${_span_cost(s):.6f}",
            f"Parent ID:   {s.parent_id or '—'}",
            f"Metadata:    {json.dumps(s.metadata, indent=2) if s.metadata else '{}'}",
            "",
            "── Prompt " + "─" * 55,
            s.prompt,
            "",
            "── Response " + "─" * 53,
            s.response,
        ]
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self._detail_text.configure(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.insert("1.0", text)
        self._detail_text.configure(state="disabled")

    def _update_status(self, visible_spans: List[Span]) -> None:
        total = len(self.tracer.spans())
        shown = len(visible_spans)
        if total == 0:
            self._status_var.set("No spans recorded.")
            return
        summ = self.tracer.summary()
        models_str = ", ".join(
            f"{m} ×{n}" for m, n in summ["models"].items())
        self._status_var.set(
            f"Showing {shown} of {total} spans"
            f"  |  Total: {summ['total_duration_ms']:.1f} ms"
            f"  |  Avg: {summ['avg_duration_ms']:.1f} ms"
            f"  |  Cost est.: ${summ['cost_estimate']:.6f}"
            f"  |  Models: {models_str}"
        )

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        try:
            items.sort(key=lambda x: float(x[0]), reverse=self._sort_rev)
        except ValueError:
            items.sort(key=lambda x: x[0], reverse=self._sort_rev)
        for idx, (_, k) in enumerate(items):
            self._tree.move(k, "", idx)

        # Update heading to show sort indicator
        for cid, label, *_ in _COLUMNS:
            indicator = ""
            if cid == self._sort_col:
                indicator = " ▲" if not self._sort_rev else " ▼"
            self._tree.heading(cid, text=label + indicator)

    def _export_json(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Export spans to JSON",
        )
        if not path:
            return
        try:
            self.tracer.save_json(path)
            messagebox.showinfo("Exported", f"Spans saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _load_json(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Load spans from JSON",
        )
        if not path:
            return
        try:
            self.tracer.load_json(path)
            self._refresh()
            messagebox.showinfo(
                "Loaded", f"Spans loaded from:\n{path}")
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))

    def _clear_all(self) -> None:
        if messagebox.askyesno("Clear All", "Delete all recorded spans?"):
            self.tracer.clear()
            self._set_detail("")
            self._refresh()

    # ── Public API ────────────────────────────────────────────────────────

    def run(self) -> None:
        """Enter the Tkinter main-loop (blocks until the window is closed)."""
        self.root.mainloop()


def launch_gui(tracer: Optional[Llmtrace] = None) -> None:
    """Open the llmtrace dashboard.

    Args:
        tracer: An existing :class:`~llmtrace.Llmtrace` instance whose spans
            will be displayed.  A fresh instance is created when *None*.
    """
    if tracer is None:
        tracer = Llmtrace()
    LlmtraceGUI(tracer).run()
