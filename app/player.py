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
from .scanner import scan_audio_files
from .settings import Settings


LOGGER = logging.getLogger("musicradio.player")
PCM_CHUNK_SIZE = 64 * 1024


@dataclass
class PlayerState:
    running: bool = False
    current_track: str | None = None
    queue_size: int = 0
    tracks_played: int = 0
    last_error: str | None = None
    hls_playlist: str = "/hls/radio.m3u8"
    started_at: float = field(default_factory=time.time)


class RadioPlayer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = PlayerState()
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._rescan_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._encoder: subprocess.Popen[bytes] | None = None
        self._decoder: subprocess.Popen[bytes] | None = None
        self._mp3_stream = Mp3Stream(settings)
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self.settings.hls_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_hls_files()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="radio-player", daemon=True)
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

    def set_mode(self, mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in {"loop", "shuffle"}:
            raise ValueError(f"Unsupported playback mode: {mode}")

        with self._lock:
            self.settings = replace(self.settings, mode=normalized)
            self._mp3_stream.update_settings(self.settings)
            self.state.last_error = None

        self._rescan_event.set()
        self._skip_event.set()
        self._terminate_process(self._decoder)
        return normalized

    def set_audio_dir(self, audio_dir: str | Path) -> Path:
        resolved = Path(audio_dir).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"Audio directory does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Audio path is not a directory: {resolved}")

        with self._lock:
            self.settings = replace(self.settings, audio_dir=resolved)
            self._mp3_stream.update_settings(self.settings)
            self.state.queue_size = 0
            self.state.current_track = None
            self.state.last_error = None

        self._rescan_event.set()
        self._skip_event.set()
        self._terminate_process(self._decoder)
        return resolved

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self.state.running,
                "audio_dir": str(self.settings.audio_dir),
                "mode": self.settings.mode,
                "current_track": self.state.current_track,
                "queue_size": self.state.queue_size,
                "tracks_played": self.state.tracks_played,
                "last_error": self.state.last_error,
                "hls_playlist": self.state.hls_playlist,
                "mp3_stream": "/stream.mp3",
                "uptime_seconds": int(time.time() - self.state.started_at),
            }

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

            tracks = scan_audio_files(self.settings.audio_dir)
            with self._lock:
                self.state.queue_size = len(tracks)

            if not tracks:
                self._set_error(f"No audio files found in {self.settings.audio_dir}")
                time.sleep(5)
                continue

            self._set_error(None)
            if self.settings.mode == "shuffle":
                random.shuffle(tracks)

            self._encoder = self._start_encoder()
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

    def _play_track(self, track: Path) -> None:
        self._skip_event.clear()
        with self._lock:
            self.state.current_track = str(track)

        LOGGER.info("Playing %s", track)
        self._decoder = self._start_decoder(track)

        try:
            assert self._decoder.stdout is not None
            assert self._encoder is not None
            assert self._encoder.stdin is not None

            while not self._stop_event.is_set() and not self._skip_event.is_set():
                chunk = self._decoder.stdout.read(PCM_CHUNK_SIZE)
                if not chunk:
                    break
                try:
                    self._encoder.stdin.write(chunk)
                    self._encoder.stdin.flush()
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
        command = self._build_decoder_command(track)
        return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

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

    def _start_encoder(self) -> subprocess.Popen[bytes]:
        command = self._build_encoder_command()
        return subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

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
            str(self.settings.segment_pattern),
            str(self.settings.playlist_path),
        ]

    def _cleanup_hls_files(self) -> None:
        for path in self.settings.hls_dir.glob("*"):
            if path.suffix.lower() in {".m3u8", ".ts", ".m4s", ".tmp"}:
                path.unlink(missing_ok=True)

    def _set_error(self, message: str | None) -> None:
        if message:
            LOGGER.warning(message)
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
