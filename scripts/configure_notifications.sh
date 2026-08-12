#!/usr/bin/env bash
# Configure SMTP/Teams notification channels in .env and verify with
# /api/admin/notify-test. Requires M365 SMTP credentials and/or a Teams
# webhook URL (see docs/operations/NOTIFICATIONS_SETUP.md).
#
# Usage:
#   MIRAI_SMTP_HOST=smtp.office365.com MIRAI_SMTP_PORT=587 \
#   MIRAI_SMTP_USER=... MIRAI_SMTP_PASSWORD=... MIRAI_SMTP_FROM=... \
#   MIRAI_TEAMS_WEBHOOK=... ./scripts/configure_notifications.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

changed=0
upsert_env() {
  local key="$1" value="$2"
  if [ -z "${value:-}" ]; then
    return 0
  fi
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '\n%s=%s\n' "$key" "$value" >> .env
  fi
  changed=1
}

upsert_env MIRAI_SMTP_HOST "${MIRAI_SMTP_HOST:-}"
upsert_env MIRAI_SMTP_PORT "${MIRAI_SMTP_PORT:-587}"
upsert_env MIRAI_SMTP_USER "${MIRAI_SMTP_USER:-}"
upsert_env MIRAI_SMTP_PASSWORD "${MIRAI_SMTP_PASSWORD:-}"
upsert_env MIRAI_SMTP_FROM "${MIRAI_SMTP_FROM:-}"
upsert_env MIRAI_SMTP_TLS "${MIRAI_SMTP_TLS:-1}"
upsert_env MIRAI_TEAMS_WEBHOOK "${MIRAI_TEAMS_WEBHOOK:-}"

if [ "$changed" = "1" ]; then
  echo "[notify] .env updated; restarting app container"
  chmod 600 .env
  docker compose up -d app
  for i in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8020/api/health > /dev/null 2>&1; then
      break
    fi
    sleep 5
  done
fi

if [ ! -f /home/kensan/.mirai_carbon_admin.cred ]; then
  echo "[notify] ERROR: /home/kensan/.mirai_carbon_admin.cred not found" >&2
  exit 1
fi

PW="$(sed -n 's/^password=//p' /home/kensan/.mirai_carbon_admin.cred)"
TOKEN="$(curl -fsS -X POST http://127.0.0.1:8020/api/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"carbon_admin\",\"password\":\"$PW\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"

echo "[notify] running notify-test"
curl -fsS -X POST http://127.0.0.1:8020/api/admin/notify-test \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
