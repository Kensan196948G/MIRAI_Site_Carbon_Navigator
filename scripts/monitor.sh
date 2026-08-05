#!/usr/bin/env bash
# Uptime monitor: checks /api/health and appends a line to the monitor log.
# On failure it optionally posts to the configured Teams webhook.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_URL="${BASE_URL:-https://carbon.mirai-dx-platform.com}"
LOG="${MONITOR_LOG:-$ROOT/logs/monitor.log}"
mkdir -p "$(dirname "$LOG")"

STAMP="$(date -Is)"
if curl -fsS --max-time 10 "$BASE_URL/api/health" > /dev/null 2>&1; then
  echo "$STAMP OK" >> "$LOG"
else
  echo "$STAMP FAIL" >> "$LOG"
  WEBHOOK="${MIRAI_TEAMS_WEBHOOK:-}"
  if [ -n "$WEBHOOK" ]; then
    curl -fsS -H 'Content-Type: application/json' \
      -d "{\"text\":\"🚨 MIRAI Carbon Navigator ヘルスチェック失敗: $STAMP\"}" \
      "$WEBHOOK" > /dev/null 2>&1 || true
  fi
  echo "$STAMP FAIL" >&2
fi
