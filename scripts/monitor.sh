#!/usr/bin/env bash
# Uptime monitor: checks /api/health and appends a line to the monitor log.
# On failure it optionally posts to the configured Teams webhook.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_URL="${BASE_URL:-https://carbon.mirai-dx-platform.com}"
LOG="${MONITOR_LOG:-$ROOT/logs/monitor.log}"
STATE_FILE="${MONITOR_STATE:-$ROOT/logs/monitor_state}"
mkdir -p "$(dirname "$LOG")"

STAMP="$(date -Is)"
if curl -fsS --max-time 10 "$BASE_URL/api/health/ready" > /dev/null 2>&1; then
  echo "$STAMP OK" >> "$LOG"
  FAILS=0
else
  echo "$STAMP FAIL" >> "$LOG"
  FAILS="$(($(cat "$STATE_FILE" 2>/dev/null || echo 0) + 1))"
  WEBHOOK="${MIRAI_TEAMS_WEBHOOK:-}"
  if [ "$FAILS" -ge 3 ] && [ -n "$WEBHOOK" ]; then
    curl -fsS -H 'Content-Type: application/json' \
      -d "{\"text\":\"🚨 MIRAI Carbon Navigator 3回連続ヘルスチェック失敗: $STAMP\"}" \
      "$WEBHOOK" > /dev/null 2>&1 || true
  fi
  echo "$STAMP FAIL" >&2
fi
echo "$FAILS" > "$STATE_FILE"
