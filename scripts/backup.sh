#!/usr/bin/env bash
# Daily PostgreSQL backup via docker compose (pg_dump).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$OUT_DIR"

echo "[backup] $(date -Is) start"
cd "$ROOT"
docker compose exec -T db pg_dump -U mirai -d mirai_carbon --format=custom \
  > "$OUT_DIR/mirai_carbon_$STAMP.dump"

# Keep the last 14 backups
ls -1t "$OUT_DIR"/mirai_carbon_*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f

SIZE="$(du -h "$OUT_DIR/mirai_carbon_$STAMP.dump" | cut -f1)"
echo "[backup] done: $OUT_DIR/mirai_carbon_$STAMP.dump ($SIZE)"
