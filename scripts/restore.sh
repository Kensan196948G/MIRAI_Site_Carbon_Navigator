#!/usr/bin/env bash
# Restore a PostgreSQL backup. Usage: scripts/restore.sh <backup-file.dump>
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <backup-file.dump>" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILE="$1"

echo "[restore] stopping app to avoid writes during restore"
cd "$ROOT"
docker compose stop app
docker compose cp "$FILE" db:/tmp/mirai_restore.dump
docker compose exec -T db pg_restore --clean --if-exists -U mirai -d mirai_carbon /tmp/mirai_restore.dump
docker compose exec -T db rm -f /tmp/mirai_restore.dump
docker compose start app
echo "[restore] done: $FILE"
