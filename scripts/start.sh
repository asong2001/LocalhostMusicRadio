#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DEFAULT_AUDIO_DIR="$PROJECT_DIR/audio"
AUDIO_DIR="${RADIO_AUDIO_DIR:-$DEFAULT_AUDIO_DIR}"
EXPLICIT_AUDIO_DIR=0

if [[ $# -gt 0 && "${1:0:2}" != "--" ]]; then
  AUDIO_DIR="$1"
  EXPLICIT_AUDIO_DIR=1
  shift
fi

if [[ "$EXPLICIT_AUDIO_DIR" -eq 0 ]]; then
  mkdir -p "$AUDIO_DIR"
elif [[ ! -d "$AUDIO_DIR" ]]; then
  echo "Audio directory does not exist: $AUDIO_DIR" >&2
  echo "Create it first or pass an existing music directory." >&2
  exit 2
fi

if [[ ! -r "$AUDIO_DIR" ]]; then
  echo "Audio directory is not readable: $AUDIO_DIR" >&2
  exit 2
fi

mkdir -p "$PROJECT_DIR/public/hls"

cd "$PROJECT_DIR"
export RADIO_BASE_DIR="$PROJECT_DIR"
export RADIO_AUDIO_DIR="$AUDIO_DIR"

exec python3 -m app.main --audio-dir "$AUDIO_DIR" "$@"
