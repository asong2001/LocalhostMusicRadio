#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <image[:tag]>" >&2
  echo "Example: $0 ghcr.io/asong2001/localhost-music-radio:latest" >&2
  exit 2
fi

IMAGE="$1"

docker build -t "$IMAGE" .
docker push "$IMAGE"

echo "Published $IMAGE"
