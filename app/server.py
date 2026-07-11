from __future__ import annotations

import json
import logging
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .player import RadioPlayer
from .settings import Settings


LOGGER = logging.getLogger("musicradio.server")


class RadioRequestHandler(SimpleHTTPRequestHandler):
    player: RadioPlayer
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/MP2T",
    }

    def __init__(self, *args: Any, public_dir: Path, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(public_dir), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(self.player.snapshot())
            return
        if path == "/stream.mp3":
            self._send_mp3_stream()
            return
        if path == "/":
            self.path = "/hls/radio.m3u8"
        else:
            self.path = path
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/skip":
            self.player.skip()
            self._send_json({"ok": True})
            return
        if self.path == "/api/rescan":
            self.player.rescan()
            self._send_json({"ok": True})
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

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_mp3_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("icy-name", "MusicRadio")
        self.end_headers()

        client = self.player.iter_mp3_stream()
        try:
            for chunk in client:
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            client.close()


def create_server(settings: Settings, player: RadioPlayer) -> ThreadingHTTPServer:
    settings.public_dir.mkdir(parents=True, exist_ok=True)

    class BoundRadioRequestHandler(RadioRequestHandler):
        pass

    BoundRadioRequestHandler.player = player

    def handler(*args: Any, **kwargs: Any) -> BoundRadioRequestHandler:
        return BoundRadioRequestHandler(*args, public_dir=settings.public_dir, **kwargs)

    return ThreadingHTTPServer((settings.host, settings.port), handler)


def run_server(settings: Settings, player: RadioPlayer) -> None:
    httpd = create_server(settings, player)
    LOGGER.info("Serving HLS at http://%s:%s/hls/radio.m3u8", settings.host, settings.port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
