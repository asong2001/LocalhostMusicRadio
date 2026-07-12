from __future__ import annotations

import json
import logging
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .settings import Settings
from .stream_manager import StreamManager


LOGGER = logging.getLogger("musicradio.web")


class WebRequestHandler(BaseHTTPRequestHandler):
    manager: StreamManager
    settings: Settings

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_html(self._render_index())
            return
        if path == "/api/status":
            self._send_json(self._status_payload())
            return
        if path == "/api/library":
            self._send_json(self.manager.library())
            return
        if path == "/api/streams":
            self._send_json({"streams": self._stream_payloads()})
            return
        if path == "/api/playlist":
            self._send_json(self._playlist_payload())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/skip":
            self.manager.skip()
            self._send_json({"ok": True})
            return
        if path == "/api/rescan" or path == "/api/library/rescan":
            self._send_json(self.manager.rescan_library())
            return
        if path == "/api/library":
            payload = self._read_json_body()
            try:
                self._send_json(self.manager.set_library_dir(str(payload.get("library_dir", ""))))
            except ValueError as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
            return
        if path == "/api/streams":
            payload = self._read_json_body()
            try:
                self._send_json(self.manager.create_stream(payload), status=201)
            except ValueError as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
            return
        if path == "/api/playlist/update":
            self._send_json(self._playlist_payload())
            return
        if path.startswith("/api/streams/") and path.endswith("/skip"):
            stream_id = path.split("/")[3]
            self.manager.skip(stream_id)
            self._send_json({"ok": True})
            return
        self.send_error(404)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/streams/"):
            stream_id = path.split("/")[3]
            try:
                self._send_json(self.manager.update_stream(stream_id, self._read_json_body()))
            except KeyError:
                self.send_error(404)
            except ValueError as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/streams/"):
            stream_id = path.split("/")[3]
            try:
                self.manager.delete_stream(stream_id)
            except KeyError:
                self.send_error(404)
                return
            self._send_json({"ok": True})
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _status_payload(self) -> dict[str, object]:
        payload = self.manager.status()
        payload["stream_url"] = self._absolute("/hls/radio.m3u8")
        payload["mp3_stream_url"] = self._absolute("/stream.mp3")
        payload["playlist_url"] = self._absolute("/playlist.m3u")
        return payload

    def _stream_payloads(self) -> list[dict[str, object]]:
        streams = []
        for stream in self.manager.list_streams():
            urls = stream.get("urls", {})
            stream["absolute_urls"] = {
                key: self._absolute(value) if value else None
                for key, value in urls.items()
            }
            streams.append(stream)
        return streams

    def _playlist_payload(self) -> dict[str, object]:
        hostname = self.headers.get("Host", "").split(":", 1)[0] or "localhost"
        entries = [
            {"name": name, "url": url}
            for name, url in self.manager.playlist_entries(hostname, self.settings.port)
        ]
        return {
            "playlist_url": self._absolute("/playlist.m3u"),
            "entries": entries,
            "entry_count": len(entries),
        }

    def _absolute(self, path: str | None) -> str | None:
        if not path:
            return None
        host_header = self.headers.get("Host", "")
        hostname = host_header.split(":", 1)[0] or "localhost"
        return f"http://{hostname}:{self.settings.port}{path}"

    def _render_index(self) -> str:
        title = escape("MusicRadio Control")
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ --bg:#f7f8f5; --panel:#fff; --ink:#1e2622; --muted:#66716b; --line:#dfe5dd; --accent:#0f766e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }}
    main {{ width:min(1180px, calc(100vw - 32px)); margin:0 auto; padding:28px 0 40px; }}
    header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:20px; }}
    h1 {{ margin:0; font-size:38px; line-height:1; }}
    h2 {{ margin:0 0 14px; font-size:18px; }}
    section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; margin-bottom:16px; }}
    .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:16px; }}
    .row {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; }}
    label {{ display:block; color:var(--muted); font-size:13px; font-weight:700; margin-bottom:6px; }}
    input, select {{ min-height:38px; border:1px solid var(--line); border-radius:7px; padding:0 10px; font:inherit; }}
    input[type="text"] {{ width:100%; }}
    button, a.button {{ min-height:38px; border:1px solid transparent; border-radius:7px; padding:0 14px; background:var(--accent); color:#fff; font-weight:700; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; }}
    button.secondary {{ background:#fff; color:var(--ink); border-color:var(--line); }}
    code {{ display:block; overflow-wrap:anywhere; padding:9px 10px; background:#f0f3ef; border-radius:7px; font-size:13px; }}
    .streams {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; }}
    .card {{ border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .muted {{ color:var(--muted); }}
    .files {{ max-height:360px; overflow:auto; border:1px solid var(--line); border-radius:8px; padding:8px; }}
    .folder-row {{ position:sticky; top:0; display:flex; gap:8px; align-items:flex-start; padding:8px 6px; background:#eaf1ed; color:var(--ink); font-weight:800; border-radius:6px; margin:6px 0 4px; overflow-wrap:anywhere; word-break:break-word; }}
    .folder-toggle {{ min-height:22px; width:24px; padding:0; border:1px solid var(--line); background:#fff; color:var(--ink); justify-content:center; flex:0 0 auto; }}
    .folder-title {{ flex:1; line-height:1.35; }}
    .folder-row input, .file-row input {{ margin-top:2px; flex:0 0 auto; }}
    .file-row {{ display:flex; gap:8px; align-items:flex-start; padding:5px 2px; border-bottom:1px solid #f0f0f0; }}
    .file-row.nested {{ margin-left:32px; }}
    .file-row span {{ white-space:normal; overflow-wrap:anywhere; word-break:break-word; line-height:1.35; }}
    .toast {{ min-height:22px; color:var(--muted); font-size:13px; }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns:1fr; }} header {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div><h1>MusicRadio</h1><div class="muted">多流本地音乐电台</div></div>
    <div class="row">
      <button id="updatePlaylistBtn" class="secondary" type="button">更新 M3U</button>
      <a id="playlistLink" class="button" href="#" target="_blank" rel="noreferrer">M3U</a>
    </div>
  </header>

  <section>
    <h2>音乐库</h2>
    <div class="row">
      <div style="flex:1"><label>扫描目录</label><input id="libraryDir" type="text"></div>
      <button id="saveLibraryBtn" type="button">保存目录</button>
      <button id="rescanBtn" class="secondary" type="button">重新扫描</button>
    </div>
    <div class="muted" id="libraryMeta" style="margin-top:8px"></div>
    <div class="muted" id="playlistMeta" style="margin-top:4px"></div>
    <div class="toast" id="toast"></div>
  </section>

  <div class="grid">
    <section>
      <h2>创建流</h2>
      <div class="row">
        <div style="flex:1"><label>显示名称</label><input id="newName" type="text" value="新电台"></div>
        <div><label>英文 ID</label><input id="newId" type="text" value="stream-1"></div>
        <div><label>格式</label><select id="newFormat"><option value="m3u8">m3u8</option><option value="mp3">mp3</option></select></div>
      </div>
      <div class="row" style="margin-top:12px"><button id="createBtn" type="button">创建</button></div>
    </section>

    <section>
      <h2>音频选择</h2>
      <div class="row">
        <input id="fileSearch" type="text" placeholder="搜索文件" style="flex:1">
        <button id="selectAllBtn" class="secondary" type="button">全选</button>
        <button id="invertBtn" class="secondary" type="button">反选</button>
        <button id="collapseAllBtn" class="secondary" type="button">折叠</button>
      </div>
      <div id="files" class="files" style="margin-top:10px"></div>
    </section>
  </div>

  <section>
    <h2>流列表</h2>
    <div id="streams" class="streams"></div>
  </section>
</main>
<script>
const state = {{ library: {{ files: [] }}, streams: [], activeStreamId: null, expandedFolders: new Set() }};
const $ = id => document.getElementById(id);
function toast(message) {{ $("toast").textContent = message || ""; }}
function escapeHtml(value) {{
  return String(value).replace(/[&<>"']/g, char => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[char]));
}}
async function api(path, options = {{}}) {{
  const response = await fetch(path, {{ cache: "no-store", ...options }});
  const text = await response.text();
  const data = text ? JSON.parse(text) : {{}};
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}}
function selectedSet() {{
  const stream = state.streams.find(item => item.id === state.activeStreamId);
  return new Set(stream ? stream.selected_files || [] : []);
}}
function activeStream() {{
  return state.streams.find(item => item.id === state.activeStreamId);
}}
function setActiveSelection(selected) {{
  const stream = activeStream();
  if (stream) stream.selected_files = Array.from(selected).sort();
}}
function folderName(path) {{
  const parts = path.split("/");
  return parts.length > 1 ? parts[0] : "根目录";
}}
function groupedFiles(files) {{
  return files.reduce((groups, file) => {{
    const folder = folderName(file.path);
    if (!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(file);
    return groups;
  }}, new Map());
}}
function renderFiles() {{
  const selected = selectedSet();
  const groups = groupedFiles(visibleFiles());
  $("files").innerHTML = Array.from(groups.entries()).map(([folder, files]) => {{
    const selectedCount = files.filter(file => selected.has(file.path)).length;
    const folderChecked = selectedCount === files.length && files.length > 0 ? "checked" : "";
    const expanded = state.expandedFolders.has(folder);
    const rows = expanded ? files.map(file => `<label class="file-row nested"><input type="checkbox" data-file="${{escapeHtml(file.path)}}" ${{selected.has(file.path) ? "checked" : ""}}><span title="${{escapeHtml(file.path)}}">${{escapeHtml(file.path)}}</span></label>`).join("") : "";
    return `<div class="folder-row"><button class="folder-toggle" type="button" data-toggle-folder="${{escapeHtml(folder)}}" title="${{expanded ? "折叠" : "展开"}}">${{expanded ? "−" : "+"}}</button><input type="checkbox" data-folder="${{escapeHtml(folder)}}" ${{folderChecked}}><span class="folder-title">${{escapeHtml(folder)}} <span class="muted">(${{selectedCount}}/${{files.length}})</span></span></div>${{rows}}`;
  }}).join("") || `<div class="muted">没有匹配的音频文件</div>`;
  $("files").querySelectorAll("input[data-folder]").forEach(input => {{
    const files = visibleFiles().filter(file => folderName(file.path) === input.dataset.folder);
    const selectedCount = files.filter(file => selected.has(file.path)).length;
    input.indeterminate = selectedCount > 0 && selectedCount < files.length;
  }});
}}
function visibleFiles() {{
  const query = $("fileSearch").value.toLowerCase();
  return state.library.files.filter(file => file.path.toLowerCase().includes(query));
}}
function renderStreams() {{
  $("streams").innerHTML = state.streams.map(stream => {{
    const urls = stream.absolute_urls || {{}};
    const selected = stream.selected_files ? stream.selected_files.length : 0;
    const active = stream.id === state.activeStreamId ? "2px solid var(--accent)" : "1px solid var(--line)";
    const streamUrl = urls.hls || urls.mp3 || "";
    return `<div class="card" style="border:${{active}}">
      <div class="row" style="justify-content:space-between"><strong>${{stream.name}}</strong><span class="muted">${{stream.format}}</span></div>
      <div class="muted">ID: ${{stream.id}} · ${{stream.enabled ? "启用" : "停用"}} · ${{stream.mode === "shuffle" ? "随机" : "顺序"}} · ${{selected}} 首</div>
      <div class="muted">当前: ${{stream.current_track ? stream.current_track.split(/[\\\\/]/).pop() : "-"}}</div>
      <div class="muted">状态: ${{stream.last_error || (stream.running ? "运行中" : "未运行")}}</div>
      <code>${{streamUrl || "-"}}</code>
      <div class="row" style="margin-top:10px">
        <button data-action="select" data-id="${{stream.id}}" type="button">选择</button>
        <button data-action="toggle" data-id="${{stream.id}}" class="secondary" type="button">${{stream.enabled ? "停用" : "启用"}}</button>
        <button data-action="mode" data-id="${{stream.id}}" class="secondary" type="button">${{stream.mode === "shuffle" ? "顺序" : "随机"}}</button>
        <button data-action="save" data-id="${{stream.id}}" class="secondary" type="button">保存并重启</button>
        <button data-action="skip" data-id="${{stream.id}}" class="secondary" type="button">跳过</button>
        <button data-action="delete" data-id="${{stream.id}}" class="secondary" type="button">删除</button>
      </div>
    </div>`;
  }}).join("");
}}
async function refresh() {{
  const status = await api("/api/status");
  state.library = await api("/api/library");
  state.streams = (await api("/api/streams")).streams;
  $("libraryDir").value = state.library.library_dir || "";
  $("rescanBtn").disabled = !!state.library.scanning;
  const fileCount = state.library.files ? state.library.files.length : 0;
  const scanText = state.library.scanning ? "扫描中..." : state.library.scanned_at ? `上次扫描: ${{new Date(state.library.scanned_at * 1000).toLocaleString()}}` : "尚未扫描";
  $("libraryMeta").textContent = `${{scanText}} · 已缓存 ${{fileCount}} 个音频文件${{state.library.error ? " · 错误: " + state.library.error : ""}}`;
  $("playlistLink").href = status.playlist_url || "#";
  if (!state.activeStreamId && state.streams.length) state.activeStreamId = state.streams[0].id;
  renderStreams();
  renderFiles();
  await refreshPlaylist(false);
}}
function checkedFiles() {{
  const stream = activeStream();
  return stream ? stream.selected_files || [] : [];
}}
async function updateStream(id, patch) {{
  await api(`/api/streams/${{id}}`, {{ method: "PATCH", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(patch) }});
  await refresh();
}}
async function refreshPlaylist(showToast = true) {{
  const playlist = await api("/api/playlist");
  const url = playlist.playlist_url ? `${{playlist.playlist_url}}?t=${{Date.now()}}` : "#";
  $("playlistLink").href = url;
  $("playlistMeta").textContent = `M3U 当前包含 ${{playlist.entry_count || 0}} 个启用电台`;
  if (showToast) toast("M3U 已更新");
}}
$("saveLibraryBtn").onclick = async () => {{ try {{ await api("/api/library", {{ method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{library_dir:$("libraryDir").value}}) }}); toast("目录已保存"); await refresh(); }} catch(e) {{ toast(e.message); }} }};
$("rescanBtn").onclick = async () => {{ await api("/api/library/rescan", {{ method:"POST" }}); toast("已开始后台扫描"); await refresh(); }};
$("updatePlaylistBtn").onclick = async () => {{ await api("/api/playlist/update", {{ method:"POST" }}); await refreshPlaylist(true); }};
$("createBtn").onclick = async () => {{ try {{ await api("/api/streams", {{ method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{ id:$("newId").value, name:$("newName").value, format:$("newFormat").value, enabled:true, mode:"loop", selected_files:[] }}) }}); toast("流已创建，请勾选音频后保存并重启"); await refresh(); await refreshPlaylist(false); }} catch(e) {{ toast(e.message); }} }};
$("fileSearch").oninput = renderFiles;
$("files").onclick = event => {{
  const button = event.target.closest("button[data-toggle-folder]");
  if (!button) return;
  const folder = button.dataset.toggleFolder;
  if (state.expandedFolders.has(folder)) state.expandedFolders.delete(folder);
  else state.expandedFolders.add(folder);
  renderFiles();
}};
$("files").onchange = event => {{
  const input = event.target.closest("input[type=checkbox]");
  if (!input) return;
  const selected = selectedSet();
  if (input.dataset.folder) {{
    visibleFiles().filter(file => folderName(file.path) === input.dataset.folder).forEach(file => {{
      if (input.checked) selected.add(file.path);
      else selected.delete(file.path);
    }});
  }} else if (input.dataset.file) {{
    if (input.checked) selected.add(input.dataset.file);
    else selected.delete(input.dataset.file);
  }}
  setActiveSelection(selected);
  renderFiles();
}};
$("selectAllBtn").onclick = () => {{
  const selected = selectedSet();
  visibleFiles().forEach(file => selected.add(file.path));
  setActiveSelection(selected);
  renderFiles();
}};
$("invertBtn").onclick = () => {{
  const selected = selectedSet();
  visibleFiles().forEach(file => selected.has(file.path) ? selected.delete(file.path) : selected.add(file.path));
  setActiveSelection(selected);
  renderFiles();
}};
$("collapseAllBtn").onclick = () => {{
  state.expandedFolders.clear();
  renderFiles();
}};
$("streams").onclick = async event => {{
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.id;
  const action = button.dataset.action;
  const stream = state.streams.find(item => item.id === id);
  if (action === "select") {{ state.activeStreamId = id; renderStreams(); renderFiles(); return; }}
  if (action === "toggle") await updateStream(id, {{ enabled: !stream.enabled }});
  if (action === "mode") await updateStream(id, {{ mode: stream.mode === "shuffle" ? "loop" : "shuffle" }});
  if (action === "save") {{ await updateStream(id, {{ selected_files: checkedFiles() }}); toast("已保存并重启该电台"); }}
  if (action === "skip") {{ await api(`/api/streams/${{id}}/skip`, {{ method:"POST" }}); await refresh(); }}
  if (action === "delete") {{ await api(`/api/streams/${{id}}`, {{ method:"DELETE" }}); state.activeStreamId = null; await refresh(); }}
}};
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


def create_web_server(settings: Settings, manager: StreamManager) -> ThreadingHTTPServer:
    class BoundWebRequestHandler(WebRequestHandler):
        pass

    BoundWebRequestHandler.manager = manager
    BoundWebRequestHandler.settings = settings

    return ThreadingHTTPServer((settings.host, settings.web_port), BoundWebRequestHandler)
