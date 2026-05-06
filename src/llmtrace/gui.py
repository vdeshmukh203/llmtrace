"""Tkinter-based span viewer for llmtrace."""
from __future__ import annotations

from typing import List, Optional

from .core import Llmtrace, Span


def launch_viewer(tracer: Optional[Llmtrace] = None) -> None:
    """Open the llmtrace span viewer.  Called by the ``llmtrace-viewer`` CLI entry point."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "tkinter is required for the GUI viewer. "
            "Install it via your OS package manager "
            "(e.g. `apt install python3-tk` on Debian/Ubuntu)."
        ) from exc

    _COLS = ("model", "duration_ms", "started_at", "prompt_preview", "response_preview")
    _COL_LABELS = {
        "model": "Model",
        "duration_ms": "Duration (ms)",
        "started_at": "Started at",
        "prompt_preview": "Prompt",
        "response_preview": "Response",
    }
    _COL_WIDTHS = {
        "model": 130,
        "duration_ms": 100,
        "started_at": 185,
        "prompt_preview": 220,
        "response_preview": 220,
    }

    def _truncate(text: str, n: int) -> str:
        text = text.replace("\n", " ")
        return text[:n] + "…" if len(text) > n else text

    class _SpanViewer(tk.Tk):
        """Main window for browsing, filtering, and inspecting LLM spans."""

        def __init__(self, tracer: Llmtrace) -> None:
            super().__init__()
            self.tracer = tracer
            self._sort_col: Optional[str] = None
            self._sort_reverse = False
            self.title("llmtrace viewer")
            self.geometry("1020x640")
            self.minsize(700, 480)
            self._build_menu()
            self._build_toolbar()
            self._build_table()
            self._build_detail_pane()
            self._build_status_bar()
            self._refresh()

        # ------------------------------------------------------------ #
        # Layout                                                         #
        # ------------------------------------------------------------ #

        def _build_menu(self) -> None:
            mb = tk.Menu(self)
            file_m = tk.Menu(mb, tearoff=0)
            file_m.add_command(label="Open JSON…", command=self._open_json)
            file_m.add_command(label="Open SQLite…", command=self._open_sqlite)
            file_m.add_separator()
            file_m.add_command(label="Save JSON…", command=self._save_json)
            file_m.add_command(label="Save SQLite…", command=self._save_sqlite)
            file_m.add_separator()
            file_m.add_command(label="Quit", command=self.destroy)
            mb.add_cascade(label="File", menu=file_m)

            edit_m = tk.Menu(mb, tearoff=0)
            edit_m.add_command(label="Clear all spans", command=self._clear_spans)
            mb.add_cascade(label="Edit", menu=edit_m)

            self.config(menu=mb)

        def _build_toolbar(self) -> None:
            bar = ttk.Frame(self, padding=(4, 4))
            bar.pack(side=tk.TOP, fill=tk.X)

            ttk.Label(bar, text="Model:").pack(side=tk.LEFT)
            self._model_var = tk.StringVar()
            ttk.Entry(bar, textvariable=self._model_var, width=16).pack(
                side=tk.LEFT, padx=(2, 8)
            )

            ttk.Label(bar, text="Min duration (ms):").pack(side=tk.LEFT)
            self._dur_var = tk.StringVar()
            ttk.Entry(bar, textvariable=self._dur_var, width=8).pack(
                side=tk.LEFT, padx=(2, 8)
            )

            ttk.Button(bar, text="Apply", command=self._apply_filter).pack(
                side=tk.LEFT, padx=2
            )
            ttk.Button(bar, text="Clear filter", command=self._clear_filter).pack(
                side=tk.LEFT, padx=2
            )
            ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
            ttk.Button(bar, text="Refresh", command=self._refresh).pack(side=tk.LEFT)

        def _build_table(self) -> None:
            outer = ttk.Frame(self)
            outer.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

            self._tree = ttk.Treeview(
                outer, columns=_COLS, show="headings", selectmode="browse"
            )
            for col in _COLS:
                self._tree.heading(
                    col,
                    text=_COL_LABELS[col],
                    command=lambda c=col: self._sort_by(c),
                )
                self._tree.column(col, width=_COL_WIDTHS[col], minwidth=60)

            vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self._tree.yview)
            hsb = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=self._tree.xview)
            self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            self._tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            outer.rowconfigure(0, weight=1)
            outer.columnconfigure(0, weight=1)

            self._tree.bind("<<TreeviewSelect>>", self._on_select)

        def _build_detail_pane(self) -> None:
            pane = ttk.LabelFrame(self, text="Span detail", padding=6)
            pane.pack(fill=tk.X, padx=4, pady=(0, 4))

            self._detail = tk.Text(
                pane,
                height=8,
                state=tk.DISABLED,
                wrap=tk.WORD,
                font=("Courier", 10),
            )
            sb = ttk.Scrollbar(pane, command=self._detail.yview)
            self._detail.configure(yscrollcommand=sb.set)
            self._detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)

        def _build_status_bar(self) -> None:
            self._status_var = tk.StringVar(value="Ready")
            ttk.Label(
                self,
                textvariable=self._status_var,
                relief=tk.SUNKEN,
                anchor=tk.W,
            ).pack(side=tk.BOTTOM, fill=tk.X)

        # ------------------------------------------------------------ #
        # Data helpers                                                   #
        # ------------------------------------------------------------ #

        def _refresh(self, spans: Optional[List[Span]] = None) -> None:
            self._tree.delete(*self._tree.get_children())
            if spans is None:
                spans = self.tracer.spans()
            for s in spans:
                self._tree.insert(
                    "",
                    tk.END,
                    iid=s.id,
                    values=(
                        s.model,
                        f"{s.duration_ms:.1f}",
                        s.started_at,
                        _truncate(s.prompt, 60),
                        _truncate(s.response, 60),
                    ),
                )
            summ = self.tracer.summary()
            self._status_var.set(
                f"Spans: {summ['count']}   "
                f"Total: {summ.get('total_duration_ms', 0):.1f} ms   "
                f"Avg: {summ.get('avg_duration_ms', 0):.1f} ms   "
                f"Est. cost: ${summ.get('cost_estimate', 0):.6f}"
            )

        def _apply_filter(self) -> None:
            model = self._model_var.get().strip() or None
            min_dur: Optional[float] = None
            if self._dur_var.get().strip():
                try:
                    min_dur = float(self._dur_var.get())
                except ValueError:
                    messagebox.showerror("Invalid input", "Duration must be a number.")
                    return
            self._refresh(self.tracer.filter(model=model, min_duration_ms=min_dur))

        def _clear_filter(self) -> None:
            self._model_var.set("")
            self._dur_var.set("")
            self._refresh()

        def _sort_by(self, col: str) -> None:
            if self._sort_col == col:
                self._sort_reverse = not self._sort_reverse
            else:
                self._sort_col = col
                self._sort_reverse = False
            spans = self.tracer.spans()
            try:
                spans.sort(
                    key=lambda s: getattr(s, col, ""), reverse=self._sort_reverse
                )
            except TypeError:
                pass
            self._refresh(spans)

        def _on_select(self, _event: object) -> None:
            sel = self._tree.selection()
            if not sel:
                return
            match = next((s for s in self.tracer.spans() if s.id == sel[0]), None)
            if match is None:
                return
            text = "\n".join([
                f"ID:         {match.id}",
                f"Model:      {match.model}",
                f"Started:    {match.started_at}",
                f"Ended:      {match.ended_at}",
                f"Duration:   {match.duration_ms:.3f} ms",
                f"Parent:     {match.parent_id or '—'}",
                f"Metadata:   {match.metadata}",
                "",
                "--- Prompt ---",
                match.prompt,
                "",
                "--- Response ---",
                match.response,
            ])
            self._detail.config(state=tk.NORMAL)
            self._detail.delete("1.0", tk.END)
            self._detail.insert(tk.END, text)
            self._detail.config(state=tk.DISABLED)

        def _clear_spans(self) -> None:
            if messagebox.askyesno("Clear spans", "Delete all recorded spans?"):
                self.tracer.clear()
                self._refresh()

        # ------------------------------------------------------------ #
        # File I/O                                                       #
        # ------------------------------------------------------------ #

        def _open_json(self) -> None:
            path = filedialog.askopenfilename(
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            if path:
                try:
                    self.tracer.load_json(path)
                    self._refresh()
                except Exception as exc:
                    messagebox.showerror("Load failed", str(exc))

        def _open_sqlite(self) -> None:
            path = filedialog.askopenfilename(
                filetypes=[("SQLite databases", "*.db *.sqlite"), ("All files", "*.*")]
            )
            if path:
                try:
                    self.tracer.load_sqlite(path)
                    self._refresh()
                except Exception as exc:
                    messagebox.showerror("Load failed", str(exc))

        def _save_json(self) -> None:
            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
            )
            if path:
                try:
                    self.tracer.save_json(path)
                except Exception as exc:
                    messagebox.showerror("Save failed", str(exc))

        def _save_sqlite(self) -> None:
            path = filedialog.asksaveasfilename(
                defaultextension=".db",
                filetypes=[("SQLite databases", "*.db")],
            )
            if path:
                try:
                    self.tracer.save_sqlite(path)
                except Exception as exc:
                    messagebox.showerror("Save failed", str(exc))

    _SpanViewer(tracer or Llmtrace()).mainloop()
