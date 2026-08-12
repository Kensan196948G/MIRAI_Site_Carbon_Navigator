#!/usr/bin/env bash
# Smoke test: health + login + dashboard.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8020}"
USERNAME="${SMOKE_USER:-admin}"
PASSWORD="${SMOKE_PASSWORD:-}"

if [ -z "$PASSWORD" ]; then
  echo "[smoke] ERROR: SMOKE_PASSWORD is required (SMOKE_USER defaults to admin)" >&2
  exit 1
fi

echo "[smoke] health"
curl -fsS "$BASE_URL/api/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["status"]=="ok"; print("health ok", d["version"])'
echo "[smoke] ready"
curl -fsS "$BASE_URL/api/health/ready" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["db"]=="ok"; print("db ok")'
echo "[smoke] login"
TOKEN="$(curl -fsS -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
echo "[smoke] dashboard"
curl -fsS "$BASE_URL/api/emissions/dashboard" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert "project_count" in d; print("dashboard ok, projects:", d["project_count"])'
echo "[smoke] PASS"
