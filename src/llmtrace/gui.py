"""Lightweight web dashboard for llmtrace.

Launch with::

    from llmtrace import Llmtrace
    from llmtrace.gui import launch_dashboard

    tracer = Llmtrace()
    # ... record spans ...
    launch_dashboard(tracer)          # opens http://localhost:8765 in your browser
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Llmtrace

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>llmtrace dashboard</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
  header{background:#1a1f2e;padding:16px 24px;border-bottom:1px solid #2d3748;display:flex;align-items:center;gap:12px}
  header h1{font-size:1.2rem;font-weight:700;color:#63b3ed;letter-spacing:-0.01em}
  header .sub{font-size:0.78rem;color:#718096}
  .stats{display:flex;gap:14px;padding:18px 24px 4px;flex-wrap:wrap}
  .stat{background:#1a1f2e;border:1px solid #2d3748;border-radius:10px;padding:14px 18px;min-width:130px}
  .stat-label{font-size:0.68rem;text-transform:uppercase;letter-spacing:.07em;color:#718096}
  .stat-value{font-size:1.45rem;font-weight:700;color:#63b3ed;margin-top:5px}
  .controls{padding:14px 24px 10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .controls input{background:#1a1f2e;border:1px solid #2d3748;border-radius:7px;color:#e2e8f0;padding:8px 13px;font-size:0.85rem;width:220px;outline:none;transition:border .15s}
  .controls input:focus{border-color:#63b3ed}
  .btn{background:#2b6cb0;border:none;border-radius:7px;color:#fff;padding:8px 16px;cursor:pointer;font-size:0.85rem;transition:background .15s}
  .btn:hover{background:#2c5282}
  .ts{font-size:0.7rem;color:#718096;margin-left:auto}
  .table-wrap{overflow-x:auto;padding:0 24px 32px}
  table{width:100%;border-collapse:collapse;font-size:0.8rem}
  thead th{background:#1a1f2e;color:#a0aec0;font-weight:500;text-align:left;padding:10px 12px;border-bottom:1px solid #2d3748;cursor:pointer;user-select:none;white-space:nowrap}
  thead th:hover{color:#63b3ed}
  tbody tr{border-bottom:1px solid #1a2030}
  tbody tr:hover{background:#181e2c}
  td{padding:9px 12px;vertical-align:top;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  td.wrap{white-space:normal;word-break:break-word;max-width:300px}
  .badge{display:inline-block;padding:2px 9px;border-radius:9999px;font-size:0.7rem;background:#1e3a5f;color:#90cdf4;white-space:nowrap}
  .dim{color:#718096;font-size:0.72rem}
  .empty{text-align:center;color:#4a5568;padding:40px;font-size:0.9rem}
  .sort-asc::after{content:" ▲"}
  .sort-desc::after{content:" ▼"}
</style>
</head>
<body>
<header>
  <h1>llmtrace</h1>
  <span class="sub">LLM call dashboard &mdash; auto-refreshes every 5 s</span>
</header>
<div class="stats" id="stats"></div>
<div class="controls">
  <input id="filter-model" placeholder="Filter by model…" oninput="applyFilter()">
  <input id="filter-prompt" placeholder="Search prompt…" oninput="applyFilter()">
  <button class="btn" onclick="fetchData()">&#8635; Refresh</button>
  <span class="ts" id="ts"></span>
</div>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th id="th-model" onclick="sortBy('model')">Model</th>
        <th id="th-duration_ms" onclick="sortBy('duration_ms')">Duration (ms)</th>
        <th id="th-started_at" onclick="sortBy('started_at')">Started (UTC)</th>
        <th>Prompt</th>
        <th>Response</th>
        <th>Tokens&nbsp;~</th>
        <th>Parent</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
</div>
<script>
var allSpans=[], sortKey='started_at', sortDir=1;

async function fetchData(){
  try{
    var[sr,sumr]=await Promise.all([fetch('/api/spans'),fetch('/api/summary')]);
    allSpans=await sr.json();
    renderStats(await sumr.json());
    applyFilter();
    document.getElementById('ts').textContent='Updated '+new Date().toLocaleTimeString();
  }catch(e){document.getElementById('ts').textContent='Fetch error: '+e.message;}
}

function renderStats(s){
  var models=Object.entries(s.models||{}).map(function(e){return e[0]+'('+e[1]+')';}).join(', ')||'—';
  document.getElementById('stats').innerHTML=
    stat('Spans',s.count)+
    stat('Avg duration',(s.avg_duration_ms||0).toFixed(1)+' ms')+
    stat('Total time',((s.total_duration_ms||0)/1000).toFixed(2)+' s')+
    stat('Est. cost','$'+(s.cost_estimate||0).toFixed(5))+
    '<div class="stat"><div class="stat-label">Models</div><div class="stat-value" style="font-size:.8rem;margin-top:8px">'+esc(models)+'</div></div>';
}
function stat(label,val){return '<div class="stat"><div class="stat-label">'+label+'</div><div class="stat-value">'+val+'</div></div>';}

function applyFilter(){
  var m=document.getElementById('filter-model').value.toLowerCase();
  var p=document.getElementById('filter-prompt').value.toLowerCase();
  var rows=allSpans.filter(function(s){return(!m||s.model.toLowerCase().includes(m))&&(!p||(s.prompt||'').toLowerCase().includes(p));});
  rows=[].concat(rows).sort(function(a,b){return(a[sortKey]<b[sortKey]?-1:a[sortKey]>b[sortKey]?1:0)*sortDir;});
  renderRows(rows);
  ['model','duration_ms','started_at'].forEach(function(k){
    var th=document.getElementById('th-'+k);
    th.className=sortKey===k?(sortDir===1?'sort-asc':'sort-desc'):'';
  });
}

function sortBy(key){sortKey===key?sortDir*=-1:(sortKey=key,sortDir=1);applyFilter();}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function approxTokens(s){return Math.round(((s.prompt||'').length+(s.response||'').length)/4);}

function renderRows(spans){
  var tb=document.getElementById('rows');
  if(!spans.length){tb.innerHTML='<tr><td colspan="7" class="empty">No spans recorded yet.</td></tr>';return;}
  tb.innerHTML=spans.map(function(s){
    var ts=esc((s.started_at||'').slice(0,19).replace('T',' '));
    return '<tr>'+
      '<td><span class="badge">'+esc(s.model)+'</span></td>'+
      '<td>'+s.duration_ms.toFixed(1)+'</td>'+
      '<td class="dim">'+ts+'</td>'+
      '<td class="wrap">'+esc((s.prompt||'').slice(0,150))+'</td>'+
      '<td class="wrap">'+esc((s.response||'').slice(0,150))+'</td>'+
      '<td class="dim">'+approxTokens(s)+'</td>'+
      '<td class="dim">'+esc(s.parent_id||'')+'</td>'+
      '</tr>';
  }).join('');
}

fetchData();
setInterval(fetchData,5000);
</script>
</body>
</html>"""


def launch_dashboard(
    tracer: "Llmtrace",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Start a local web dashboard for *tracer* on ``http://localhost:<port>``.

    The dashboard auto-refreshes every 5 seconds and exposes two JSON
    endpoints used by the frontend:

    * ``GET /api/spans``   — full span list
    * ``GET /api/summary`` — aggregate statistics

    The HTTP server blocks the calling thread.  Press Ctrl-C to stop.

    Parameters
    ----------
    tracer:
        The :class:`~llmtrace.Llmtrace` instance whose spans to display.
    port:
        TCP port to listen on (default ``8765``).
    open_browser:
        If ``True`` (default), open the dashboard in the default browser
        half a second after the server starts.
    """

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:  # silence request log
            pass

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", _HTML.encode())
            elif self.path == "/api/spans":
                self._send(200, "application/json", json.dumps(tracer.export()).encode())
            elif self.path == "/api/summary":
                self._send(200, "application/json", json.dumps(tracer.summary()).encode())
            else:
                self._send(404, "text/plain", b"Not found")

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://localhost:{port}"
    print(f"llmtrace dashboard → {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
