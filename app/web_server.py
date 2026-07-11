from __future__ import annotations

import json
import logging
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .player import RadioPlayer
from .settings import Settings


LOGGER = logging.getLogger("musicradio.web")


class WebRequestHandler(BaseHTTPRequestHandler):
    player: RadioPlayer
    settings: Settings

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._send_html(self._render_index())
            return
        if self.path == "/api/status":
            payload = self.player.snapshot()
            payload["stream_url"] = self._stream_url()
            payload["web_port"] = self.settings.web_port
            self._send_json(payload)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/skip":
            self.player.skip()
            self._send_json({"ok": True})
            return
        if self.path == "/api/rescan":
            self.player.rescan()
            self._send_json({"ok": True})
            return
        if self.path == "/api/audio-dir":
            payload = self._read_json_body()
            audio_dir = str(payload.get("audio_dir", "")).strip()
            if not audio_dir:
                self._send_json({"ok": False, "error": "audio_dir is required"}, status=400)
                return
            try:
                resolved = self.player.set_audio_dir(audio_dir)
            except ValueError as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            self._send_json({"ok": True, "audio_dir": str(resolved)})
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

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

    def _stream_url(self) -> str:
        host_header = self.headers.get("Host", "")
        hostname = host_header.split(":", 1)[0] or "localhost"
        return f"http://{hostname}:{self.settings.port}/hls/radio.m3u8"

    def _render_index(self) -> str:
        title = "MusicRadio Control"
        escaped_title = escape(title)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8f5;
      --panel: #ffffff;
      --ink: #1e2622;
      --muted: #66716b;
      --line: #dfe5dd;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --warn: #b45309;
      --ok-bg: #dff4ea;
      --ok-ink: #17633a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    main {{
      width: min(1040px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }}
    header {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1.05;
      font-weight: 760;
    }}
    .subtitle {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .status-pill {{
      min-width: 116px;
      padding: 9px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      text-align: center;
      font-weight: 700;
      color: var(--warn);
    }}
    .status-pill.running {{
      color: var(--ok-ink);
      background: var(--ok-bg);
      border-color: #b7e5ca;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 16px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      line-height: 1.2;
    }}
    dl {{
      display: grid;
      grid-template-columns: 132px minmax(0, 1fr);
      gap: 12px 14px;
      margin: 0;
      align-items: start;
    }}
    dt {{
      color: var(--muted);
      font-size: 13px;
    }}
    dd {{
      margin: 0;
      min-width: 0;
      word-break: break-word;
      font-size: 14px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    button, a.button {{
      appearance: none;
      border: 1px solid transparent;
      border-radius: 7px;
      background: var(--accent);
      color: white;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 0 14px;
      font-size: 14px;
      font-weight: 700;
      text-decoration: none;
    }}
    button.secondary, a.button.secondary {{
      background: #ffffff;
      color: var(--ink);
      border-color: var(--line);
    }}
    button:hover, a.button:hover {{
      background: var(--accent-strong);
    }}
    button.secondary:hover, a.button.secondary:hover {{
      background: #eef3ef;
    }}
    .field {{
      display: grid;
      gap: 7px;
      margin-top: 12px;
    }}
    label {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    input {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 11px;
      color: var(--ink);
      background: #ffffff;
      font: inherit;
      font-size: 14px;
    }}
    input:focus {{
      outline: 2px solid rgba(15, 118, 110, 0.18);
      border-color: var(--accent);
    }}
    audio {{
      width: 100%;
      margin-top: 8px;
    }}
    code {{
      display: block;
      width: 100%;
      overflow-wrap: anywhere;
      padding: 10px 11px;
      border-radius: 7px;
      background: #f0f3ef;
      color: #25312c;
      font-size: 13px;
      line-height: 1.4;
    }}
    .toast {{
      min-height: 20px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 760px) {{
      header {{
        align-items: stretch;
        flex-direction: column;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
      dl {{
        grid-template-columns: 1fr;
        gap: 4px;
      }}
      dd {{
        margin-bottom: 8px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>MusicRadio</h1>
        <p class="subtitle">本地音乐电台控制台</p>
      </div>
      <div id="runningPill" class="status-pill">读取中</div>
    </header>

    <div class="grid">
      <section>
        <h2>播放状态</h2>
        <dl>
          <dt>当前曲目</dt>
          <dd id="currentTrack">-</dd>
          <dt>队列数量</dt>
          <dd id="queueSize">-</dd>
          <dt>已播放</dt>
          <dd id="tracksPlayed">-</dd>
          <dt>运行时间</dt>
          <dd id="uptime">-</dd>
          <dt>扫描目录</dt>
          <dd id="audioDir">-</dd>
          <dt>最近错误</dt>
          <dd id="lastError">-</dd>
        </dl>
        <div class="actions">
          <button id="refreshBtn" type="button">刷新</button>
          <button id="skipBtn" class="secondary" type="button">跳过当前</button>
          <button id="rescanBtn" class="secondary" type="button">重新扫描</button>
        </div>
        <div id="toast" class="toast"></div>
      </section>

      <section>
        <h2>直播地址</h2>
        <code id="streamUrl">-</code>
        <audio id="audioPlayer" controls preload="none"></audio>
        <div class="actions">
          <a id="openStream" class="button" href="#" target="_blank" rel="noreferrer">打开流</a>
          <button id="copyBtn" class="secondary" type="button">复制地址</button>
        </div>
      </section>

      <section>
        <h2>扫描目录</h2>
        <div class="field">
          <label for="audioDirInput">音频目录</label>
          <input id="audioDirInput" type="text" autocomplete="off" spellcheck="false">
        </div>
        <div class="actions">
          <button id="saveAudioDirBtn" type="button">保存并扫描</button>
        </div>
      </section>
    </div>
  </main>
  <script>
    const elements = {{
      runningPill: document.getElementById("runningPill"),
      currentTrack: document.getElementById("currentTrack"),
      queueSize: document.getElementById("queueSize"),
      tracksPlayed: document.getElementById("tracksPlayed"),
      uptime: document.getElementById("uptime"),
      audioDir: document.getElementById("audioDir"),
      audioDirInput: document.getElementById("audioDirInput"),
      lastError: document.getElementById("lastError"),
      streamUrl: document.getElementById("streamUrl"),
      openStream: document.getElementById("openStream"),
      audioPlayer: document.getElementById("audioPlayer"),
      toast: document.getElementById("toast"),
    }};

    function formatSeconds(value) {{
      const seconds = Number(value || 0);
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = seconds % 60;
      return `${{h}}h ${{m}}m ${{s}}s`;
    }}

    function basename(path) {{
      if (!path) return "-";
      return String(path).split(/[\\\\/]/).pop() || path;
    }}

    function setToast(message) {{
      elements.toast.textContent = message || "";
    }}

    async function refresh() {{
      try {{
        const response = await fetch("/api/status", {{ cache: "no-store" }});
        const data = await response.json();
        elements.runningPill.textContent = data.running ? "运行中" : "已停止";
        elements.runningPill.classList.toggle("running", Boolean(data.running));
        elements.currentTrack.textContent = basename(data.current_track);
        elements.queueSize.textContent = data.queue_size ?? "-";
        elements.tracksPlayed.textContent = data.tracks_played ?? "-";
        elements.uptime.textContent = formatSeconds(data.uptime_seconds);
        elements.audioDir.textContent = data.audio_dir || "-";
        if (document.activeElement !== elements.audioDirInput) {{
          elements.audioDirInput.value = data.audio_dir || "";
        }}
        elements.lastError.textContent = data.last_error || "-";
        elements.streamUrl.textContent = data.stream_url || "-";
        elements.openStream.href = data.stream_url || "#";
        if (data.stream_url && elements.audioPlayer.src !== data.stream_url) {{
          elements.audioPlayer.src = data.stream_url;
        }}
      }} catch (error) {{
        elements.runningPill.textContent = "连接失败";
        elements.runningPill.classList.remove("running");
        setToast(String(error));
      }}
    }}

    async function postAction(path, label) {{
      setToast(`${{label}}...`);
      const response = await fetch(path, {{ method: "POST" }});
      if (!response.ok) throw new Error(`${{label}}失败`);
      setToast(`${{label}}完成`);
      await refresh();
    }}

    async function saveAudioDir() {{
      const audioDir = elements.audioDirInput.value.trim();
      if (!audioDir) {{
        setToast("请输入音频目录");
        return;
      }}
      setToast("正在切换扫描目录...");
      const response = await fetch("/api/audio-dir", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ audio_dir: audioDir }}),
      }});
      const data = await response.json();
      if (!response.ok) {{
        setToast(data.error || "切换目录失败");
        return;
      }}
      setToast("扫描目录已更新");
      await refresh();
    }}

    document.getElementById("refreshBtn").addEventListener("click", refresh);
    document.getElementById("skipBtn").addEventListener("click", () => postAction("/api/skip", "跳过"));
    document.getElementById("rescanBtn").addEventListener("click", () => postAction("/api/rescan", "扫描"));
    document.getElementById("saveAudioDirBtn").addEventListener("click", saveAudioDir);
    document.getElementById("copyBtn").addEventListener("click", async () => {{
      const url = elements.streamUrl.textContent;
      await navigator.clipboard.writeText(url);
      setToast("地址已复制");
    }});

    refresh();
    window.setInterval(refresh, 5000);
  </script>
</body>
</html>"""


def create_web_server(settings: Settings, player: RadioPlayer) -> ThreadingHTTPServer:
    class BoundWebRequestHandler(WebRequestHandler):
        pass

    BoundWebRequestHandler.player = player
    BoundWebRequestHandler.settings = settings

    return ThreadingHTTPServer((settings.host, settings.web_port), BoundWebRequestHandler)
