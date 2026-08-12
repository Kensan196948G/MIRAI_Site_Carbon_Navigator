#!/usr/bin/env bash
# Production deploy: build + start compose, wait for health, run smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Local production smoke uses the rotated admin credential when present.
if [ -z "${SMOKE_PASSWORD:-}" ] && [ -f /home/kensan/.mirai_carbon_admin.cred ]; then
  SMOKE_USER="${SMOKE_USER:-carbon_admin}"
  SMOKE_PASSWORD="$(sed -n 's/^password=//p' /home/kensan/.mirai_carbon_admin.cred)"
fi
export SMOKE_USER SMOKE_PASSWORD

echo "[deploy] commit: $(git rev-parse HEAD)"
docker compose up -d --build db app

echo "[deploy] waiting for health..."
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8020/api/health > /dev/null 2>&1; then
    echo "[deploy] healthy after ${i}0s"
    break
  fi
  sleep 10
done

"$ROOT/scripts/smoke.sh"
echo "[deploy] DONE"
