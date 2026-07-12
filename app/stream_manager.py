from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import RLock, Thread
import time

from .config_store import ConfigStore, RadioConfig, StreamConfig, validate_stream_config
from .mp3_stream import Mp3ClientIterator
from .player import PlaybackConfig, RadioPlayer
from .scanner import scan_audio_files
from .settings import Settings


class StreamManager:
    def __init__(self, settings: Settings, store: ConfigStore) -> None:
        self.settings = settings
        self.store = store
        self._lock = RLock()
        self.config = store.load()
        self.players: dict[str, RadioPlayer] = {}
        self._library_files: list[dict[str, object]] = []
        self._library_scanned_at: float | None = None
        self._library_scanning = False
        self._library_error: str | None = None

    @property
    def library_dir(self) -> Path:
        return Path(self.config.library_dir).resolve()

    def start(self) -> None:
        with self._lock:
            for stream in self.config.streams:
                if stream.enabled:
                    self._ensure_player(stream).start()

    def stop(self) -> None:
        with self._lock:
            players = list(self.players.values())
            self.players.clear()
        for player in players:
            player.stop()

    def library(self) -> dict[str, object]:
        with self._lock:
            return self._library_payload_locked()

    def rescan_library(self) -> dict[str, object]:
        with self._lock:
            if self._library_scanning:
                return self._library_payload_locked()
            self._library_scanning = True
            self._library_error = None
            library_dir = self.library_dir
        Thread(target=self._scan_library_worker, args=(library_dir,), daemon=True).start()
        with self._lock:
            return self._library_payload_locked()

    def set_library_dir(self, library_dir: str) -> dict[str, object]:
        resolved = Path(library_dir).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"Library directory does not exist: {resolved}")
        with self._lock:
            self.config = replace(self.config, library_dir=str(resolved))
            self._library_files = []
            self._library_scanned_at = None
            self._library_error = None
            self.store.save(self.config)
            self._restart_all_locked()
            return self._library_payload_locked()

    def list_streams(self) -> list[dict[str, object]]:
        with self._lock:
            return [self._stream_payload(stream) for stream in self.config.streams]

    def create_stream(self, payload: dict[str, object]) -> dict[str, object]:
        stream = self._stream_from_payload(payload)
        with self._lock:
            if self._find_stream(stream.id):
                raise ValueError(f"Stream already exists: {stream.id}")
            self.config = replace(self.config, streams=[*self.config.streams, stream])
            self.store.save(self.config)
            if stream.enabled:
                self._ensure_player(stream).start()
            return self._stream_payload(stream)

    def update_stream(self, stream_id: str, payload: dict[str, object]) -> dict[str, object]:
        with self._lock:
            current = self._require_stream(stream_id)
            updated = replace(
                current,
                name=str(payload.get("name", current.name)).strip() or current.name,
                format=str(payload.get("format", current.format)),
                enabled=bool(payload.get("enabled", current.enabled)),
                mode=str(payload.get("mode", current.mode)),
                selected_files=list(payload.get("selected_files", current.selected_files)),
            )
            validate_stream_config(updated)
            streams = [updated if item.id == stream_id else item for item in self.config.streams]
            self.config = replace(self.config, streams=streams)
            self.store.save(self.config)
            self._restart_stream_locked(updated)
            return self._stream_payload(updated)

    def delete_stream(self, stream_id: str) -> None:
        with self._lock:
            self._require_stream(stream_id)
            player = self.players.pop(stream_id, None)
            if player:
                player.stop()
            self.config = replace(
                self.config,
                streams=[stream for stream in self.config.streams if stream.id != stream_id],
            )
            self.store.save(self.config)

    def skip(self, stream_id: str | None = None) -> None:
        player = self._default_player() if stream_id is None else self.players.get(stream_id)
        if player:
            player.skip()

    def status(self, stream_id: str | None = None) -> dict[str, object]:
        with self._lock:
            if stream_id is None:
                player = self._default_player()
                return player.snapshot() if player else {}
            stream = self._require_stream(stream_id)
            player = self.players.get(stream_id)
            return player.snapshot() if player else self._stream_payload(stream)

    def iter_mp3_stream(self, stream_id: str) -> Mp3ClientIterator | None:
        with self._lock:
            player = self.players.get(stream_id)
            if player is None or player.stream_format != "mp3":
                return None
            return player.iter_mp3_stream()

    def compatible_stream_id(self, stream_format: str) -> str | None:
        default_id = "default" if stream_format == "m3u8" else "default-mp3"
        with self._lock:
            default = self._find_stream(default_id)
            if default and default.enabled and default.selected_files:
                return default.id
            for stream in self.config.streams:
                if stream.format == stream_format and stream.enabled and stream.selected_files:
                    return stream.id
            return default.id if default and default.enabled else None

    def hls_public_path(self, stream_id: str) -> Path | None:
        with self._lock:
            stream = self._find_stream(stream_id)
            if stream is None or stream.format != "m3u8":
                return None
            return self._hls_dir(stream) / "radio.m3u8"

    def playlist_entries(self, hostname: str, port: int) -> list[tuple[str, str]]:
        base_url = f"http://{hostname}:{port}"
        entries = []
        with self._lock:
            for stream in self.config.streams:
                if not stream.enabled:
                    continue
                if stream.format == "m3u8":
                    url = f"{base_url}{self._public_hls_url(stream)}"
                else:
                    url = f"{base_url}{self._public_mp3_url(stream)}"
                entries.append((stream.name, url))
        return entries

    def _stream_from_payload(self, payload: dict[str, object]) -> StreamConfig:
        stream = StreamConfig(
            id=str(payload.get("id", "")).strip(),
            name=str(payload.get("name", "")).strip(),
            format=str(payload.get("format", "m3u8")).strip(),
            enabled=bool(payload.get("enabled", True)),
            mode=str(payload.get("mode", "loop")).strip(),
            selected_files=list(payload.get("selected_files", [])),
        )
        validate_stream_config(stream)
        return stream

    def _stream_payload(self, stream: StreamConfig) -> dict[str, object]:
        player = self.players.get(stream.id)
        payload = player.snapshot() if player else {
            "id": stream.id,
            "name": stream.name,
            "format": stream.format,
            "enabled": stream.enabled,
            "running": False,
            "mode": stream.mode,
            "selected_count": len(stream.selected_files),
            "last_error": None if stream.enabled else "Stream is disabled",
        }
        payload["selected_files"] = list(stream.selected_files)
        payload["urls"] = self._urls(stream)
        return payload

    def _urls(self, stream: StreamConfig) -> dict[str, str | None]:
        if stream.format == "m3u8":
            return {
                "hls": self._public_hls_url(stream),
                "mp3": None,
            }
        return {
            "hls": None,
            "mp3": self._public_mp3_url(stream),
        }

    def _public_hls_url(self, stream: StreamConfig) -> str:
        if stream.id == "default":
            return "/hls/radio.m3u8"
        return f"/streams/{stream.id}/hls/radio.m3u8"

    def _public_mp3_url(self, stream: StreamConfig) -> str:
        if stream.id == "default-mp3":
            return "/stream.mp3"
        return f"/streams/{stream.id}/stream.mp3"

    def _ensure_player(self, stream: StreamConfig) -> RadioPlayer:
        player = self.players.get(stream.id)
        config = PlaybackConfig(
            id=stream.id,
            name=stream.name,
            format=stream.format,
            enabled=stream.enabled,
            mode=stream.mode,
            selected_files=tuple(stream.selected_files),
            library_dir=self.library_dir,
            hls_dir=self._hls_dir(stream),
        )
        if player is None:
            player = RadioPlayer(self.settings, config)
            self.players[stream.id] = player
        else:
            player.update_config(config)
        return player

    def _hls_dir(self, stream: StreamConfig) -> Path:
        if stream.id == "default":
            return self.settings.hls_dir
        return self.settings.public_dir / "streams" / stream.id / "hls"

    def _find_stream(self, stream_id: str) -> StreamConfig | None:
        return next((stream for stream in self.config.streams if stream.id == stream_id), None)

    def _require_stream(self, stream_id: str) -> StreamConfig:
        stream = self._find_stream(stream_id)
        if stream is None:
            raise KeyError(stream_id)
        return stream

    def _restart_stream_locked(self, stream: StreamConfig) -> None:
        player = self.players.pop(stream.id, None)
        if player:
            player.stop()
        if stream.enabled:
            self._ensure_player(stream).start()

    def _restart_all_locked(self) -> None:
        players = list(self.players.values())
        self.players.clear()
        for player in players:
            player.stop()
        for stream in self.config.streams:
            if stream.enabled:
                self._ensure_player(stream).start()

    def _default_player(self) -> RadioPlayer | None:
        return self.players.get("default") or next(iter(self.players.values()), None)

    def _library_payload_locked(self) -> dict[str, object]:
        return {
            "library_dir": str(self.library_dir),
            "files": list(self._library_files),
            "scanning": self._library_scanning,
            "scanned_at": self._library_scanned_at,
            "error": self._library_error,
        }

    def _scan_library_worker(self, library_dir: Path) -> None:
        files: list[dict[str, object]] = []
        error: str | None = None
        try:
            for path in scan_audio_files(library_dir):
                files.append(
                    {
                        "path": str(path.relative_to(library_dir)).replace("\\", "/"),
                        "name": path.name,
                        "size": path.stat().st_size,
                    }
                )
        except Exception as exc:  # pragma: no cover - defensive around NAS/filesystem errors
            error = str(exc)
        with self._lock:
            if library_dir == self.library_dir and error is None:
                self._library_files = files
                self._library_scanned_at = time.time()
                for player in self.players.values():
                    player.rescan()
            self._library_error = error
            self._library_scanning = False
