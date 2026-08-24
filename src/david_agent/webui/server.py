"""Read-only observability dashboard over ~/.david-agent/sessions.db.

Not a chat UI — DSH already does that well (Fase 13). This is CLAUDE.md
§20's other half: seeing what the runtime actually did — sessions, model
calls with real cost/latency, tool call audit trail. Stdlib HTTP server,
vanilla JS, no build step, no new dependency, matching the project's own
"no frontend complejo" principle until there's a real reason for one.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from david_agent.memory.sqlite import SQLiteMemoryStore

DEFAULT_PORT = 8900

INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>david-agent dashboard</title>
<style>
  :root { color-scheme: dark; }
  body { font: 14px/1.4 -apple-system, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; display: flex; height: 100vh; }
  #sidebar { width: 320px; border-right: 1px solid #30363d; overflow-y: auto; flex-shrink: 0; }
  #sidebar h1 { font-size: 15px; padding: 16px; margin: 0; border-bottom: 1px solid #30363d; }
  #stats { padding: 12px 16px; font-size: 12px; color: #8b949e; border-bottom: 1px solid #30363d; }
  .session { padding: 10px 16px; border-bottom: 1px solid #161b22; cursor: pointer; }
  .session:hover { background: #161b22; }
  .session.active { background: #1f2937; border-left: 3px solid #58a6ff; }
  .session .id { font-family: monospace; font-size: 11px; color: #8b949e; }
  .session .meta { font-size: 12px; color: #8b949e; margin-top: 2px; }
  #main { flex: 1; overflow-y: auto; padding: 20px 28px; }
  .empty { color: #8b949e; padding: 40px; text-align: center; }
  .msg { margin-bottom: 14px; padding: 10px 14px; border-radius: 8px; max-width: 80%; white-space: pre-wrap; }
  .msg.user { background: #1f2937; margin-left: auto; }
  .msg.assistant { background: #161b22; border: 1px solid #30363d; }
  .msg .role { font-size: 11px; color: #8b949e; margin-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0 24px; font-size: 12px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 500; }
  h2 { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin: 24px 0 8px; }
  .err { color: #f85149; }
  code { background: #161b22; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
</style>
</head>
<body>
<div id="sidebar">
  <h1>david-agent</h1>
  <div id="stats">loading…</div>
  <div id="sessions"></div>
</div>
<div id="main"><div class="empty">Select a session</div></div>
<script>
async function loadSessions() {
  const res = await fetch('/api/sessions');
  const data = await res.json();
  document.getElementById('stats').textContent =
    `${data.sessions.length} sessions · $${data.total_cost.toFixed(4)} total`;
  const el = document.getElementById('sessions');
  el.innerHTML = '';
  for (const s of data.sessions) {
    const div = document.createElement('div');
    div.className = 'session';
    div.innerHTML = `<div class="id">${s.id}</div><div class="meta">${s.agent_name} · ${s.created_at}</div>`;
    div.onclick = () => selectSession(s.id, div);
    el.appendChild(div);
  }
}

async function selectSession(id, el) {
  document.querySelectorAll('.session').forEach(s => s.classList.remove('active'));
  el.classList.add('active');
  const res = await fetch(`/api/sessions/${id}`);
  const data = await res.json();
  const main = document.getElementById('main');
  let html = '';
  for (const m of data.messages) {
    html += `<div class="msg ${m.role}"><div class="role">${m.role}</div>${escapeHtml(m.content)}</div>`;
  }
  html += '<h2>Model calls</h2><table><tr><th>Provider</th><th>Model</th><th>In/Out tok</th><th>Cost</th><th>When</th></tr>';
  for (const c of data.model_calls) {
    const cost = c.cost_usd != null ? '$' + c.cost_usd.toFixed(4) : 'n/a';
    html += `<tr><td>${c.provider}</td><td>${c.model}</td><td>${c.input_tokens ?? '?'}/${c.output_tokens ?? '?'}</td><td>${cost}</td><td>${c.created_at}</td></tr>`;
  }
  html += '</table>';
  if (data.tool_calls.length) {
    html += '<h2>Tool calls</h2><table><tr><th>Tool</th><th>Args</th><th>Result</th><th>When</th></tr>';
    for (const t of data.tool_calls) {
      const result = t.error ? `<span class="err">${escapeHtml(t.error)}</span>` : escapeHtml((t.result || '').slice(0, 200));
      html += `<tr><td><code>${t.tool_name}</code></td><td><code>${escapeHtml(t.args_json)}</code></td><td>${result}</td><td>${t.created_at}</td></tr>`;
    }
    html += '</table>';
  }
  main.innerHTML = html || '<div class="empty">No data in this session</div>';
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
}

loadSessions();
</script>
</body>
</html>
"""


def _make_handler(store: SQLiteMemoryStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[webui] {self.address_string()} - {fmt % args}")

        def _send_json(self, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.rstrip("/")

            if path == "" or path == "/":
                body = INDEX_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/sessions":
                sessions = store.list_sessions(limit=100)
                total_cost = 0.0
                for s in sessions:
                    detail = store.get_session_detail(s.id)
                    total_cost += sum(c["cost_usd"] or 0 for c in detail["model_calls"])
                self._send_json(
                    {
                        "sessions": [{"id": s.id, "agent_name": s.agent_name, "created_at": s.created_at} for s in sessions],
                        "total_cost": total_cost,
                    }
                )
                return

            if path.startswith("/api/sessions/"):
                session_id = path[len("/api/sessions/") :]
                self._send_json(store.get_session_detail(session_id))
                return

            self.send_response(404)
            self.end_headers()

    return Handler


def main() -> None:
    store = SQLiteMemoryStore()
    server = ThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), _make_handler(store))
    print(f"david-agent dashboard: http://127.0.0.1:{DEFAULT_PORT}")
    print(f"reading: {store.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
