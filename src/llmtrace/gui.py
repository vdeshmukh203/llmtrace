"""Lightweight web dashboard for llmtrace spans.

Launch the dashboard with::

    from llmtrace.gui import Dashboard
    dash = Dashboard(tracer)
    dash.open()           # starts server and opens browser
    dash.serve_forever()  # blocks; Ctrl-C to stop

Or as a one-liner::

    Dashboard(tracer).open().serve_forever()

The dashboard is served by Python's built-in :mod:`http.server` and requires
no external dependencies.  It exposes three endpoints:

``GET /``
    Main HTML dashboard page.
``GET /api/spans``
    All spans as a JSON array.
``GET /api/summary``
    Aggregated statistics as a JSON object.
``GET /api/export``
    Download spans as ``spans.json``.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Llmtrace

# ---------------------------------------------------------------------------
# Embedded HTML/CSS/JS (zero external dependencies)
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>llmtrace dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2d3148;
    --text: #e2e8f0; --muted: #8892a4; --accent: #6366f1;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --font: 'Segoe UI', system-ui, sans-serif; --mono: 'Cascadia Code', 'Fira Code', monospace;
  }
  body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; min-height: 100vh; }
  a { color: var(--accent); text-decoration: none; }
  /* Layout */
  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; gap: 14px; }
  header h1 { font-size: 18px; font-weight: 700; letter-spacing: -.3px; }
  header .badge { background: var(--accent); color: #fff; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 99px; letter-spacing: .5px; }
  #refresh-indicator { margin-left: auto; font-size: 12px; color: var(--muted); }
  main { padding: 24px; max-width: 1400px; margin: 0 auto; }
  /* Stats cards */
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 28px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; }
  .card .label { font-size: 11px; text-transform: uppercase; letter-spacing: .8px; color: var(--muted); margin-bottom: 8px; }
  .card .value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .card .sub { font-size: 11px; color: var(--muted); margin-top: 4px; }
  /* Toolbar */
  .toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; align-items: center; }
  .toolbar input, .toolbar select { background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 7px 11px; font-size: 13px; outline: none; }
  .toolbar input:focus, .toolbar select:focus { border-color: var(--accent); }
  .toolbar label { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 5px; }
  .btn { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 7px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn:hover { opacity: .85; }
  .btn-ghost { background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
  .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
  /* Timeline */
  .timeline-section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; margin-bottom: 24px; }
  .timeline-section h2 { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .6px; color: var(--muted); margin-bottom: 14px; }
  .timeline-bar-wrap { position: relative; height: 22px; background: var(--bg); border-radius: 4px; margin-bottom: 6px; overflow: hidden; }
  .timeline-bar { position: absolute; height: 100%; border-radius: 4px; min-width: 4px; opacity: .85; cursor: pointer; transition: opacity .15s; }
  .timeline-bar:hover { opacity: 1; }
  .tl-label { font-size: 11px; color: var(--muted); margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }
  /* Table */
  .table-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .7px; color: var(--muted); padding: 11px 14px; border-bottom: 1px solid var(--border); background: var(--bg); cursor: pointer; user-select: none; white-space: nowrap; }
  th:hover { color: var(--text); }
  th .sort-arrow { margin-left: 4px; opacity: .4; }
  th.sorted .sort-arrow { opacity: 1; color: var(--accent); }
  td { padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; font-size: 13px; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(99,102,241,.05); }
  .model-pill { background: rgba(99,102,241,.18); color: var(--accent); border-radius: 99px; padding: 2px 8px; font-size: 11px; font-weight: 600; white-space: nowrap; }
  .dur { font-family: var(--mono); font-size: 12px; }
  .dur.fast { color: var(--green); }
  .dur.mid  { color: var(--yellow); }
  .dur.slow { color: var(--red); }
  .text-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .expand-btn { color: var(--accent); font-size: 11px; cursor: pointer; margin-left: 4px; }
  .expanded .text-cell { white-space: pre-wrap; max-width: none; overflow: visible; }
  /* Modal */
  .modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 100; align-items: center; justify-content: center; }
  .modal-bg.open { display: flex; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; max-width: 640px; width: 95%; max-height: 80vh; overflow-y: auto; }
  .modal h3 { font-size: 15px; margin-bottom: 16px; }
  .modal pre { background: var(--bg); border-radius: 8px; padding: 16px; font-family: var(--mono); font-size: 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
  .modal-close { float: right; cursor: pointer; color: var(--muted); font-size: 18px; line-height: 1; }
  /* Empty state */
  .empty { text-align: center; padding: 60px 20px; color: var(--muted); }
  .empty .icon { font-size: 40px; margin-bottom: 12px; }
  /* Models bar */
  .model-bars { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
  .model-bar-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
  .model-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
  /* Tooltip */
  [data-tip] { position: relative; }
  [data-tip]:hover::after { content: attr(data-tip); position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); background: #000; color: #fff; font-size: 11px; padding: 4px 8px; border-radius: 5px; white-space: nowrap; z-index: 50; pointer-events: none; }
  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<header>
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="11" r="10" stroke="#6366f1" stroke-width="2"/><path d="M7 11h8M11 7v8" stroke="#6366f1" stroke-width="2" stroke-linecap="round"/></svg>
  <h1>llmtrace</h1>
  <span class="badge">dashboard</span>
  <span id="refresh-indicator">auto-refresh in <span id="countdown">5</span>s</span>
</header>
<main>
  <div class="stats" id="stats"></div>
  <div class="timeline-section">
    <h2>Timeline</h2>
    <div id="timeline"></div>
  </div>
  <div class="toolbar">
    <input id="filter-model" placeholder="Filter by model…" oninput="applyFilters()">
    <input id="filter-min-dur" type="number" min="0" placeholder="Min duration (ms)" oninput="applyFilters()">
    <label><input type="checkbox" id="filter-has-parent" onchange="applyFilters()"> Has parent</label>
    <button class="btn-ghost" onclick="clearFilters()">Clear filters</button>
    <button class="btn" onclick="exportJson()">⬇ Export JSON</button>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th onclick="sortBy('model')" id="th-model">Model <span class="sort-arrow">↕</span></th>
          <th onclick="sortBy('duration_ms')" id="th-duration_ms">Duration <span class="sort-arrow">↕</span></th>
          <th onclick="sortBy('started_at')" id="th-started_at" class="sorted">Started <span class="sort-arrow">↓</span></th>
          <th>Prompt</th>
          <th>Response</th>
          <th>Metadata</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display:none">
      <div class="icon">🔍</div>
      <div>No spans match the current filters.</div>
    </div>
  </div>
</main>
<!-- Detail modal -->
<div class="modal-bg" id="modal-bg" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <span class="modal-close" onclick="closeModalForce()">✕</span>
    <h3 id="modal-title">Span detail</h3>
    <pre id="modal-body"></pre>
  </div>
</div>
<script>
const MODEL_COLORS = ['#6366f1','#22c55e','#eab308','#ef4444','#3b82f6','#a855f7','#f97316','#06b6d4'];
let allSpans = [], filtered = [], sortKey = 'started_at', sortAsc = false;

function modelColor(name) {
  let h = 0; for (let c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffffffff;
  return MODEL_COLORS[Math.abs(h) % MODEL_COLORS.length];
}

function durClass(ms) { return ms < 500 ? 'fast' : ms < 2000 ? 'mid' : 'slow'; }
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function fetchData() {
  const [sr, sumr] = await Promise.all([fetch('/api/spans'), fetch('/api/summary')]);
  allSpans = await sr.json();
  const sum = await sumr.json();
  renderStats(sum);
  applyFilters();
  renderTimeline();
}

function renderStats(sum) {
  const models = sum.models || {};
  const modelNames = Object.keys(models);
  document.getElementById('stats').innerHTML = `
    <div class="card"><div class="label">Total spans</div><div class="value">${sum.count}</div></div>
    <div class="card"><div class="label">Total duration</div><div class="value">${fmt(sum.total_duration_ms)}</div><div class="sub">ms</div></div>
    <div class="card"><div class="label">Avg duration</div><div class="value">${fmt(sum.avg_duration_ms??0)}</div><div class="sub">ms</div></div>
    <div class="card"><div class="label">Est. cost</div><div class="value">$${(sum.cost_estimate??0).toFixed(4)}</div><div class="sub">at $0.002/kchar</div></div>
    <div class="card" style="grid-column:span 2">
      <div class="label">Models (${modelNames.length})</div>
      <div class="model-bars">${modelNames.map(m=>`<div class="model-bar-item"><div class="model-swatch" style="background:${modelColor(m)}"></div>${escHtml(m)}: ${models[m]}</div>`).join('')}</div>
    </div>`;
}

function fmt(n) { return n == null ? '—' : Number(n).toLocaleString('en', {maximumFractionDigits:1}); }

function renderTimeline() {
  const tl = document.getElementById('timeline');
  if (!allSpans.length) { tl.innerHTML = '<div style="color:var(--muted);font-size:12px">No spans yet.</div>'; return; }
  const starts = allSpans.map(s => new Date(s.started_at).getTime());
  const ends   = allSpans.map(s => new Date(s.ended_at).getTime() + (s.duration_ms||0));
  const tMin = Math.min(...starts), tMax = Math.max(...ends);
  const range = tMax - tMin || 1;
  tl.innerHTML = allSpans.slice(0, 40).map((s, i) => {
    const left = ((new Date(s.started_at).getTime() - tMin) / range * 100).toFixed(2);
    const w = Math.max((s.duration_ms / range * 100), 0.3).toFixed(2);
    const color = modelColor(s.model);
    return `<div class="tl-label">${escHtml(s.model)}: ${escHtml((s.prompt||'').slice(0,60))}</div>
    <div class="timeline-bar-wrap" data-tip="${s.duration_ms.toFixed(1)}ms">
      <div class="timeline-bar" style="left:${left}%;width:${w}%;background:${color}" onclick='openModal(${JSON.stringify(JSON.stringify(s))})'></div>
    </div>`;
  }).join('');
  if (allSpans.length > 40) tl.innerHTML += `<div style="color:var(--muted);font-size:11px;margin-top:6px">Showing first 40 of ${allSpans.length} spans.</div>`;
}

function applyFilters() {
  const model = document.getElementById('filter-model').value.trim().toLowerCase();
  const minDur = parseFloat(document.getElementById('filter-min-dur').value) || 0;
  const hasParent = document.getElementById('filter-has-parent').checked;
  filtered = allSpans.filter(s =>
    (!model || s.model.toLowerCase().includes(model)) &&
    s.duration_ms >= minDur &&
    (!hasParent || s.parent_id != null)
  );
  sortAndRender();
}

function clearFilters() {
  document.getElementById('filter-model').value = '';
  document.getElementById('filter-min-dur').value = '';
  document.getElementById('filter-has-parent').checked = false;
  applyFilters();
}

function sortBy(key) {
  if (sortKey === key) sortAsc = !sortAsc; else { sortKey = key; sortAsc = false; }
  document.querySelectorAll('th').forEach(th => { th.classList.remove('sorted'); th.querySelector('.sort-arrow').textContent = '↕'; });
  const th = document.getElementById('th-' + key);
  if (th) { th.classList.add('sorted'); th.querySelector('.sort-arrow').textContent = sortAsc ? '↑' : '↓'; }
  sortAndRender();
}

function sortAndRender() {
  const s = [...filtered].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (typeof av === 'string') av = av.toLowerCase(), bv = (bv||'').toLowerCase();
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ? 1 : -1;
    return 0;
  });
  renderTable(s);
}

function renderTable(spans) {
  const tbody = document.getElementById('tbody');
  const empty = document.getElementById('empty');
  if (!spans.length) { tbody.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';
  tbody.innerHTML = spans.map(s => {
    const color = modelColor(s.model);
    const meta = Object.keys(s.metadata||{}).length ? JSON.stringify(s.metadata) : '—';
    const dc = durClass(s.duration_ms);
    return `<tr>
      <td><span class="model-pill" style="background:${color}22;color:${color}">${escHtml(s.model)}</span>${s.parent_id?'<br><span style="font-size:10px;color:var(--muted)">↳ child</span>':''}</td>
      <td class="dur ${dc}">${s.duration_ms.toFixed(1)}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${new Date(s.started_at).toLocaleTimeString()}</td>
      <td class="text-cell">${escHtml((s.prompt||'').slice(0,120))}<span class="expand-btn" onclick='openModal(${JSON.stringify(JSON.stringify(s))})'>…</span></td>
      <td class="text-cell">${escHtml((s.response||'').slice(0,120))}<span class="expand-btn" onclick='openModal(${JSON.stringify(JSON.stringify(s))})'>…</span></td>
      <td style="font-size:11px;color:var(--muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(meta)}</td>
    </tr>`;
  }).join('');
}

function openModal(jsonStr) {
  const s = JSON.parse(jsonStr);
  document.getElementById('modal-title').textContent = `Span · ${s.model} · ${s.duration_ms.toFixed(1)}ms`;
  document.getElementById('modal-body').textContent = JSON.stringify(s, null, 2);
  document.getElementById('modal-bg').classList.add('open');
}
function closeModal(e) { if (e.target === document.getElementById('modal-bg')) closeModalForce(); }
function closeModalForce() { document.getElementById('modal-bg').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModalForce(); });

async function exportJson() {
  const a = document.createElement('a');
  a.href = '/api/export'; a.download = 'spans.json'; a.click();
}

// Auto-refresh
let countdown = 5;
setInterval(() => {
  countdown--;
  document.getElementById('countdown').textContent = countdown;
  if (countdown <= 0) { countdown = 5; fetchData(); }
}, 1000);

fetchData();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    tracer: Llmtrace  # injected by Dashboard

    def log_message(self, fmt, *args):  # silence access log
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._respond(200, "text/html; charset=utf-8", _HTML.encode())
        elif path == "/api/spans":
            data = json.dumps(self.tracer.export(), ensure_ascii=False).encode()
            self._respond(200, "application/json", data)
        elif path == "/api/summary":
            data = json.dumps(self.tracer.summary(), ensure_ascii=False).encode()
            self._respond(200, "application/json", data)
        elif path == "/api/export":
            data = json.dumps(self.tracer.export(), indent=2, ensure_ascii=False).encode()
            self._respond(
                200,
                "application/json",
                data,
                extra_headers={"Content-Disposition": 'attachment; filename="spans.json"'},
            )
        else:
            self._respond(404, "text/plain", b"Not found")

    def _respond(self, code, content_type, body, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Dashboard class
# ---------------------------------------------------------------------------

class Dashboard:
    """Serve a web dashboard for a :class:`~llmtrace.core.Llmtrace` instance.

    Parameters
    ----------
    tracer:
        The tracer whose spans will be displayed.
    host:
        Hostname to bind (default ``"127.0.0.1"``).
    port:
        TCP port to bind (default ``5173``; any free port is chosen when 0).

    Examples
    --------
    ::

        from llmtrace import Llmtrace
        from llmtrace.gui import Dashboard

        tracer = Llmtrace()
        # … record some spans …
        dash = Dashboard(tracer)
        dash.open()          # starts server and opens browser tab
        dash.serve_forever() # blocks; Ctrl-C to stop
    """

    def __init__(
        self,
        tracer: Llmtrace,
        host: str = "127.0.0.1",
        port: int = 5173,
    ) -> None:
        self.tracer = tracer
        self.host = host
        self.port = port
        self._server: HTTPServer | None = None

    # ------------------------------------------------------------------

    def start(self) -> Dashboard:
        """Start the HTTP server in a background daemon thread.

        Returns *self* for chaining (``dash.start().open()``).
        """
        handler_cls = type("_H", (_Handler,), {"tracer": self.tracer})
        self._server = HTTPServer((self.host, self.port), handler_cls)
        self.port = self._server.server_address[1]  # update if port was 0
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        return self

    def open(self) -> Dashboard:
        """Start the server (if not already running) and open a browser tab.

        Returns *self* for chaining.
        """
        if self._server is None:
            self.start()
        webbrowser.open(self.url)
        return self

    def serve_forever(self) -> None:
        """Block until interrupted (Ctrl-C).

        Starts the server if not already running.
        """
        if self._server is None:
            self.start()
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._server.shutdown()

    def shutdown(self) -> None:
        """Stop the HTTP server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    @property
    def url(self) -> str:
        """Base URL of the running dashboard, e.g. ``http://127.0.0.1:5173``."""
        return f"http://{self.host}:{self.port}"
