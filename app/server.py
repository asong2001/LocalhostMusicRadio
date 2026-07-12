from __future__ import annotations

import json
import logging
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .settings import Settings
from .stream_manager import StreamManager


LOGGER = logging.getLogger("musicradio.server")


class RadioRequestHandler(SimpleHTTPRequestHandler):
    manager: StreamManager
    settings: Settings
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".m3u": "audio/x-mpegurl",
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/MP2T",
    }

    def __init__(self, *args: Any, public_dir: Path, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(public_dir), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(self.manager.status())
            return
        if path == "/playlist.m3u":
            self._send_m3u_playlist()
            return
        if path == "/stream.mp3":
            stream_id = self.manager.compatible_stream_id("mp3")
            self._send_mp3_stream(stream_id or "default-mp3")
            return
        if path.startswith("/streams/") and path.endswith("/stream.mp3"):
            stream_id = path.split("/")[2]
            self._send_mp3_stream(stream_id)
            return
        if (
            path == "/"
            or path == "/hls/radio.m3u8"
            or path == "/streams/default/hls/radio.m3u8"
            or path.startswith("/hls/segment_")
        ):
            self.path = self._compatible_hls_path(path)
        else:
            self.path = path
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/skip":
            self.manager.skip()
            self._send_json({"ok": True})
            return
        if path == "/api/rescan":
            self._send_json(self.manager.rescan_library())
            return
        self.send_error(404)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Pragma", "no-cache")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, payload: dict[str, object] | list[dict[str, object]]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_m3u_playlist(self) -> None:
        body = build_m3u_playlist(self.manager.playlist_entries(self._hostname(), self.settings.port)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "audio/x-mpegurl; charset=utf-8")
        self.send_header("Content-Disposition", 'inline; filename="musicradio.m3u"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_mp3_stream(self, stream_id: str) -> None:
        client = self.manager.iter_mp3_stream(stream_id)
        if client is None:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("icy-name", "MusicRadio")
        self.end_headers()

        try:
            for chunk in client:
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            client.close()

    def _hostname(self) -> str:
        host_header = self.headers.get("Host", "")
        return host_header.split(":", 1)[0] or "localhost"

    def _compatible_hls_path(self, path: str) -> str:
        stream_id = self.manager.compatible_stream_id("m3u8")
        filename = "radio.m3u8" if path in {"/", "/hls/radio.m3u8"} else Path(path).name
        if not stream_id or stream_id == "default":
            return f"/hls/{filename}"
        return f"/streams/{stream_id}/hls/{filename}"


def build_m3u_playlist(entries: list[tuple[str, str]]) -> str:
    lines = ["#EXTM3U"]
    for name, url in entries:
        safe_name = name.replace('"', "'")
        lines.append(f'#EXTINF:-1 tvg-name="{safe_name}" group-title="Radio",{safe_name}')
        lines.append(url)
    lines.append("")
    return "\n".join(lines)


def create_server(settings: Settings, manager: StreamManager) -> ThreadingHTTPServer:
    settings.public_dir.mkdir(parents=True, exist_ok=True)

    class BoundRadioRequestHandler(RadioRequestHandler):
        pass

    BoundRadioRequestHandler.manager = manager
    BoundRadioRequestHandler.settings = settings

    def handler(*args: Any, **kwargs: Any) -> BoundRadioRequestHandler:
        return BoundRadioRequestHandler(*args, public_dir=settings.public_dir, **kwargs)

    return ThreadingHTTPServer((settings.host, settings.port), handler)


def run_server(settings: Settings, manager: StreamManager) -> None:
    httpd = create_server(settings, manager)
    LOGGER.info("Serving HLS at http://%s:%s/hls/radio.m3u8", settings.host, settings.port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
