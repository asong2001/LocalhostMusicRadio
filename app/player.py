from __future__ import annotations

import logging
import random
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from .mp3_stream import Mp3ClientIterator, Mp3Stream
from .settings import Settings


LOGGER = logging.getLogger("musicradio.player")
PCM_CHUNK_SIZE = 64 * 1024
STREAM_FORMATS = {"m3u8", "mp3"}


@dataclass(frozen=True)
class PlaybackConfig:
    id: str = "default"
    name: str = "MusicRadio"
    format: str = "m3u8"
    enabled: bool = True
    mode: str = "loop"
    selected_files: tuple[str, ...] = ()
    library_dir: Path = Path()
    hls_dir: Path | None = None


@dataclass
class PlayerState:
    running: bool = False
    current_track: str | None = None
    queue_size: int = 0
    tracks_played: int = 0
    last_error: str | None = None
    started_at: float = field(default_factory=time.time)


class RadioPlayer:
    def __init__(self, settings: Settings, config: PlaybackConfig | None = None) -> None:
        self.settings = settings
        self.config = config or PlaybackConfig(
            mode=settings.mode,
            library_dir=settings.audio_dir,
            hls_dir=settings.hls_dir,
        )
        self.state = PlayerState()
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._rescan_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._encoder: subprocess.Popen[bytes] | None = None
        self._decoder: subprocess.Popen[bytes] | None = None
        self._mp3_stream = Mp3Stream(settings)
        self._lock = threading.Lock()

    @property
    def stream_id(self) -> str:
        return self.config.id

    @property
    def stream_format(self) -> str:
        return self.config.format

    @property
    def hls_dir(self) -> Path:
        return self.config.hls_dir or self.settings.hls_dir

    @property
    def playlist_path(self) -> Path:
        return self.hls_dir / "radio.m3u8"

    @property
    def segment_pattern(self) -> Path:
        return self.hls_dir / "segment_%05d.ts"

    def start(self) -> None:
        if not self.config.enabled:
            self._set_error("Stream is disabled")
            return
        if self._thread and self._thread.is_alive():
            return

        if self.stream_format == "m3u8":
            self.hls_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_hls_files()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"radio-player-{self.stream_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._skip_event.set()
        self._terminate_process(self._decoder)
        self._terminate_process(self._encoder)
        self._mp3_stream.stop()
        if self._thread:
            self._thread.join(timeout=10)

    def skip(self) -> None:
        self._skip_event.set()
        self._terminate_process(self._decoder)

    def rescan(self) -> None:
        self._rescan_event.set()

    def update_config(self, config: PlaybackConfig) -> None:
        with self._lock:
            self.config = config
            self._mp3_stream.update_settings(self.settings)
            self.state.queue_size = 0
            self.state.current_track = None
            self.state.last_error = None
        self._rescan_event.set()
        self._skip_event.set()
        self._terminate_process(self._decoder)

    def set_mode(self, mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in {"loop", "shuffle"}:
            raise ValueError(f"Unsupported playback mode: {mode}")
        self.update_config(replace(self.config, mode=normalized))
        return normalized

    def set_audio_dir(self, audio_dir: str | Path) -> Path:
        resolved = Path(audio_dir).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"Audio directory does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Audio path is not a directory: {resolved}")
        self.update_config(replace(self.config, library_dir=resolved))
        return resolved

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "id": self.config.id,
                "name": self.config.name,
                "format": self.config.format,
                "enabled": self.config.enabled,
                "running": self.state.running,
                "audio_dir": str(self.config.library_dir),
                "mode": self.config.mode,
                "selected_count": len(self.config.selected_files),
                "current_track": self.state.current_track,
                "queue_size": self.state.queue_size,
                "tracks_played": self.state.tracks_played,
                "last_error": self.state.last_error,
                "hls_playlist": self.hls_path(),
                "mp3_stream": self.mp3_path(),
                "uptime_seconds": int(time.time() - self.state.started_at),
            }

    def hls_path(self) -> str | None:
        if self.stream_format != "m3u8":
            return None
        return f"/streams/{self.stream_id}/hls/radio.m3u8"

    def mp3_path(self) -> str | None:
        if self.stream_format != "mp3":
            return None
        return f"/streams/{self.stream_id}/stream.mp3"

    def iter_mp3_stream(self) -> Mp3ClientIterator:
        return self._mp3_stream.iter_client()

    def _run(self) -> None:
        with self._lock:
            self.state.running = True

        while not self._stop_event.is_set():
            if shutil.which(self.settings.ffmpeg_bin) is None:
                self._set_error(f"FFmpeg not found: {self.settings.ffmpeg_bin}")
                time.sleep(5)
                continue

            tracks = self._selected_tracks()
            with self._lock:
                self.state.queue_size = len(tracks)

            if not tracks:
                self._set_error("No selected audio files")
                time.sleep(5)
                continue

            self._set_error(None)
            if self.config.mode == "shuffle":
                random.shuffle(tracks)

            if self.stream_format == "m3u8":
                self._encoder = self._start_hls_encoder()

            try:
                for track in tracks:
                    if self._stop_event.is_set():
                        break
                    self._play_track(track)
                    if self._rescan_event.is_set():
                        self._rescan_event.clear()
                        break
            finally:
                self._terminate_process(self._encoder)
                self._encoder = None

        with self._lock:
            self.state.running = False
            self.state.current_track = None

    def _selected_tracks(self) -> list[Path]:
        tracks = []
        for relative_path in self.config.selected_files:
            path = (self.config.library_dir / relative_path).resolve()
            try:
                path.relative_to(self.config.library_dir)
            except ValueError:
                continue
            if path.is_file():
                tracks.append(path)
        return tracks

    def _play_track(self, track: Path) -> None:
        self._skip_event.clear()
        with self._lock:
            self.state.current_track = str(track)

        LOGGER.info("[%s] Playing %s", self.stream_id, track)
        self._decoder = self._start_decoder(track)

        try:
            assert self._decoder.stdout is not None

            while not self._stop_event.is_set() and not self._skip_event.is_set():
                chunk = self._decoder.stdout.read(PCM_CHUNK_SIZE)
                if not chunk:
                    break
                try:
                    if self.stream_format == "m3u8":
                        assert self._encoder is not None
                        assert self._encoder.stdin is not None
                        self._encoder.stdin.write(chunk)
                        self._encoder.stdin.flush()
                    elif self.stream_format == "mp3":
                        self._mp3_stream.write_pcm(chunk)
                except BrokenPipeError:
                    self._set_error("FFmpeg encoder pipe closed")
                    break

            return_code = self._decoder.wait(timeout=5)
            if return_code not in (0, None) and not self._skip_event.is_set():
                self._set_error(f"Decoder exited with code {return_code}: {track}")
        except subprocess.TimeoutExpired:
            self._terminate_process(self._decoder)
        finally:
            self._terminate_process(self._decoder)
            self._decoder = None
            with self._lock:
                self.state.tracks_played += 1

    def _start_decoder(self, track: Path) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            self._build_decoder_command(track),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def _build_decoder_command(self, track: Path) -> list[str]:
        return [
            self.settings.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-i",
            str(track),
            "-vn",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(self.settings.sample_rate),
            "-ac",
            str(self.settings.channels),
            "pipe:1",
        ]

    def _start_hls_encoder(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            self._build_encoder_command(),
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def _build_encoder_command(self) -> list[str]:
        return [
            self.settings.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-re",
            "-f",
            "s16le",
            "-ar",
            str(self.settings.sample_rate),
            "-ac",
            str(self.settings.channels),
            "-i",
            "pipe:0",
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            self.settings.audio_bitrate,
            "-f",
            "hls",
            "-hls_time",
            str(self.settings.hls_time),
            "-hls_list_size",
            str(self.settings.hls_list_size),
            "-hls_allow_cache",
            "0",
            "-hls_flags",
            "delete_segments+omit_endlist",
            "-hls_segment_filename",
            str(self.segment_pattern),
            str(self.playlist_path),
        ]

    def _cleanup_hls_files(self) -> None:
        for path in self.hls_dir.glob("*"):
            if path.suffix.lower() in {".m3u8", ".ts", ".m4s", ".tmp"}:
                path.unlink(missing_ok=True)

    def _set_error(self, message: str | None) -> None:
        if message:
            LOGGER.warning("[%s] %s", self.stream_id, message)
        with self._lock:
            self.state.last_error = message

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes] | None) -> None:
        if process is None or process.poll() is not None:
            return

        if shutil.which("kill") is not None:
            try:
                process.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                return
        else:
            process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
