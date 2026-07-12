from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .settings import Settings


STREAM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class StreamConfig:
    id: str
    name: str
    format: str
    enabled: bool = True
    mode: str = "loop"
    selected_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RadioConfig:
    library_dir: str
    streams: list[StreamConfig]


def validate_stream_config(stream: StreamConfig) -> None:
    if not STREAM_ID_PATTERN.match(stream.id):
        raise ValueError("Stream id must use letters, numbers, hyphen, or underscore")
    if stream.format not in {"m3u8", "mp3"}:
        raise ValueError("Stream format must be m3u8 or mp3")
    if stream.mode not in {"loop", "shuffle"}:
        raise ValueError("Stream mode must be loop or shuffle")
    if not stream.name.strip():
        raise ValueError("Stream name is required")


class ConfigStore:
    def __init__(self, path: Path, settings: Settings) -> None:
        self.path = path
        self.settings = settings

    def load(self) -> RadioConfig:
        if not self.path.exists():
            config = self._default_config()
            self.save(config)
            return config

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        streams = [StreamConfig(**item) for item in payload.get("streams", [])]
        config = RadioConfig(
            library_dir=str(Path(payload.get("library_dir", self.settings.audio_dir)).resolve()),
            streams=streams,
        )
        self._validate(config)
        return config

    def save(self, config: RadioConfig) -> None:
        self._validate(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "library_dir": config.library_dir,
            "streams": [asdict(stream) for stream in config.streams],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            delete=False,
        ) as temp_file:
            temp_file.write(text)
            temp_path = Path(temp_file.name)
        temp_path.replace(self.path)

    def _default_config(self) -> RadioConfig:
        library_dir = self.settings.audio_dir.resolve()
        return RadioConfig(
            library_dir=str(library_dir),
            streams=[
                StreamConfig(
                    id="default",
                    name="MusicRadio HLS",
                    format="m3u8",
                    enabled=True,
                    mode=self.settings.mode,
                    selected_files=[],
                ),
                StreamConfig(
                    id="default-mp3",
                    name="MusicRadio MP3",
                    format="mp3",
                    enabled=True,
                    mode=self.settings.mode,
                    selected_files=[],
                ),
            ],
        )

    def _validate(self, config: RadioConfig) -> None:
        ids = set()
        for stream in config.streams:
            validate_stream_config(stream)
            if stream.id in ids:
                raise ValueError(f"Duplicate stream id: {stream.id}")
            ids.add(stream.id)
