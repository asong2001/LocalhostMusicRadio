from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    audio_dir: Path
    public_dir: Path
    hls_dir: Path
    host: str
    port: int
    web_port: int
    mode: str
    ffmpeg_bin: str
    audio_bitrate: str
    mp3_bitrate: str
    sample_rate: int
    channels: int
    hls_time: int
    hls_list_size: int

    @property
    def playlist_path(self) -> Path:
        return self.hls_dir / "radio.m3u8"

    @property
    def segment_pattern(self) -> Path:
        return self.hls_dir / "segment_%05d.ts"


@dataclass(frozen=True)
class SettingsOverrides:
    audio_dir: str | None = None
    public_dir: str | None = None
    hls_dir: str | None = None
    host: str | None = None
    port: int | None = None
    web_port: int | None = None
    mode: str | None = None
    ffmpeg_bin: str | None = None


def load_settings(overrides: SettingsOverrides | None = None) -> Settings:
    overrides = overrides or SettingsOverrides()
    base_dir = Path(os.getenv("RADIO_BASE_DIR", Path.cwd())).resolve()
    public_dir = Path(
        overrides.public_dir or os.getenv("RADIO_PUBLIC_DIR", base_dir / "public")
    ).resolve()
    hls_dir = Path(
        overrides.hls_dir or os.getenv("RADIO_HLS_DIR", public_dir / "hls")
    ).resolve()

    return Settings(
        audio_dir=Path(
            overrides.audio_dir or os.getenv("RADIO_AUDIO_DIR", base_dir / "audio")
        ).resolve(),
        public_dir=public_dir,
        hls_dir=hls_dir,
        host=overrides.host or os.getenv("RADIO_HOST", "0.0.0.0"),
        port=overrides.port or int(os.getenv("RADIO_PORT", "8000")),
        web_port=overrides.web_port or int(os.getenv("RADIO_WEB_PORT", "8001")),
        mode=(overrides.mode or os.getenv("RADIO_MODE", "loop")).lower(),
        ffmpeg_bin=overrides.ffmpeg_bin or os.getenv("RADIO_FFMPEG_BIN", "ffmpeg"),
        audio_bitrate=os.getenv("RADIO_AUDIO_BITRATE", "128k"),
        mp3_bitrate=os.getenv("RADIO_MP3_BITRATE", "128k"),
        sample_rate=int(os.getenv("RADIO_SAMPLE_RATE", "44100")),
        channels=int(os.getenv("RADIO_CHANNELS", "2")),
        hls_time=int(os.getenv("RADIO_HLS_TIME", "6")),
        hls_list_size=int(os.getenv("RADIO_HLS_LIST_SIZE", "8")),
    )
