#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DEFAULT_AUDIO_DIR="$PROJECT_DIR/audio"
AUDIO_DIR="${RADIO_AUDIO_HOST_DIR:-$DEFAULT_AUDIO_DIR}"
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

mkdir -p "$PROJECT_DIR/public/hls" "$PROJECT_DIR/config"

if command -v realpath >/dev/null 2>&1; then
  AUDIO_DIR="$(realpath "$AUDIO_DIR")"
fi

cd "$PROJECT_DIR"
export RADIO_AUDIO_HOST_DIR="$AUDIO_DIR"

exec docker compose up -d --build "$@"
