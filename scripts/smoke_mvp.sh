#!/usr/bin/env bash
# Smoke test for the MVP review environment.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8021}"
USERNAME="${SMOKE_USER:-demo_admin}"
PASSWORD="${SMOKE_PASSWORD:-DemoAdmin!2026}"

echo "[smoke-mvp] health"
curl -fsS "$BASE_URL/api/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["status"]=="ok"; print("health ok", d["version"])'
echo "[smoke-mvp] ready"
curl -fsS "$BASE_URL/api/health/ready" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["db"]=="ok"; print("db ok")'
echo "[smoke-mvp] meta"
curl -fsS "$BASE_URL/api/meta" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["demo_mode"] is True; print("demo mode ok")'
echo "[smoke-mvp] static assets"
for path in / /static/css/style.css /static/js/app.js; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL$path")"
  [ "$code" = "200" ] || { echo "FAIL: $path -> $code" >&2; exit 1; }
done
echo "static assets ok"
echo "[smoke-mvp] login"
TOKEN="$(curl -fsS -X POST "$BASE_URL/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
echo "[smoke-mvp] dashboard + demo data"
curl -fsS "$BASE_URL/api/emissions/dashboard" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["project_count"] == 2, d; print("dashboard ok, projects:", d["project_count"])'
curl -fsS "$BASE_URL/api/demo/status" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["project_count"] == 2, d; print("demo status ok")'
echo "[smoke-mvp] PASS"
