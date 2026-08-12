#!/usr/bin/env bash
# Verify the integrity of a PostgreSQL custom-format backup without restoring it.
# Usage: scripts/verify_backup.sh <backup-file.dump>
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <backup-file.dump>" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILE="$1"

if [ -f "$FILE.sha256" ]; then
  (cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$FILE").sha256")
fi

cd "$ROOT"
docker compose cp "$FILE" db:/tmp/verify_backup.dump
docker compose exec -T db pg_restore --list /tmp/verify_backup.dump > /dev/null
docker compose exec -T db rm -f /tmp/verify_backup.dump
echo "[verify] OK: $FILE"
