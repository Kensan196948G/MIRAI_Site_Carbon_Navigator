#!/usr/bin/env bash
# Production deploy: build + start compose, wait for health, run smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[deploy] commit: $(git rev-parse HEAD)"
docker compose up -d --build db app

echo "[deploy] waiting for health..."
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8010/api/health > /dev/null 2>&1; then
    echo "[deploy] healthy after ${i}0s"
    break
  fi
  sleep 10
done

"$ROOT/scripts/smoke.sh"
echo "[deploy] DONE"
