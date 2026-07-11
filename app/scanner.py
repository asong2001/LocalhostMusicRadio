from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}


def scan_audio_files(audio_dir: Path) -> list[Path]:
    if not audio_dir.exists():
        return []

    files = [
        path
        for path in audio_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files, key=lambda item: str(item).lower())
