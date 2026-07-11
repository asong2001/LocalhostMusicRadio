from __future__ import annotations

import logging
import queue
import subprocess
import threading
from dataclasses import dataclass

from .settings import Settings


LOGGER = logging.getLogger("musicradio.mp3")
MP3_CHUNK_SIZE = 16 * 1024
CLIENT_QUEUE_SIZE = 256


@dataclass(eq=False)
class Mp3Client:
    queue: queue.Queue[bytes | None]


class Mp3Stream:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._process: subprocess.Popen[bytes] | None = None
        self._reader_thread: threading.Thread | None = None
        self._clients: set[Mp3Client] = set()
        self._lock = threading.Lock()

    def update_settings(self, settings: Settings) -> None:
        with self._lock:
            self.settings = settings

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            clients = list(self._clients)
            self._clients.clear()

        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()

        for client in clients:
            self._offer(client.queue, None)

    def write_pcm(self, chunk: bytes) -> None:
        if not chunk:
            return

        process = self._ensure_process()
        if process is None or process.stdin is None:
            return

        try:
            process.stdin.write(chunk)
            process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            LOGGER.warning("MP3 encoder pipe closed: %s", error)
            self.stop()

    def iter_client(self) -> "Mp3ClientIterator":
        client = Mp3Client(queue.Queue(maxsize=CLIENT_QUEUE_SIZE))
        with self._lock:
            self._clients.add(client)
        return Mp3ClientIterator(self, client)

    def remove_client(self, client: Mp3Client) -> None:
        with self._lock:
            self._clients.discard(client)

    def _ensure_process(self) -> subprocess.Popen[bytes] | None:
        with self._lock:
            if self._process and self._process.poll() is None:
                return self._process

            command = self._build_command()
            try:
                self._process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as error:
                LOGGER.warning("Unable to start MP3 encoder: %s", error)
                self._process = None
                return None

            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                name="mp3-stream-reader",
                daemon=True,
            )
            self._reader_thread.start()
            return self._process

    def _build_command(self) -> list[str]:
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
            "libmp3lame",
            "-b:a",
            self.settings.mp3_bitrate,
            "-f",
            "mp3",
            "pipe:1",
        ]

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return

        while True:
            chunk = process.stdout.read(MP3_CHUNK_SIZE)
            if not chunk:
                break
            self._broadcast(chunk)

        with self._lock:
            if self._process is process:
                self._process = None

    def _broadcast(self, chunk: bytes) -> None:
        with self._lock:
            clients = list(self._clients)

        for client in clients:
            self._offer(client.queue, chunk)

    @staticmethod
    def _offer(client_queue: queue.Queue[bytes | None], chunk: bytes | None) -> None:
        try:
            client_queue.put_nowait(chunk)
        except queue.Full:
            try:
                client_queue.get_nowait()
                client_queue.put_nowait(chunk)
            except queue.Empty:
                pass


class Mp3ClientIterator:
    def __init__(self, stream: Mp3Stream, client: Mp3Client) -> None:
        self.stream = stream
        self.client = client

    def __iter__(self) -> "Mp3ClientIterator":
        return self

    def __next__(self) -> bytes:
        chunk = self.client.queue.get()
        if chunk is None:
            raise StopIteration
        return chunk

    def close(self) -> None:
        self.stream.remove_client(self.client)
