#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-localhost-music-radio:latest}"

docker build -t "$IMAGE" .

echo "Built $IMAGE"
