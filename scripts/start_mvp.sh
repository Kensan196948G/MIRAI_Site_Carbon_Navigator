#!/usr/bin/env bash
# Start the MVP/Prototype review environment (local, development-only).
# Seeded with fictional demo data; never points at production data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export MIRAI_ENV="${MIRAI_ENV:-development}"
export MIRAI_SEED_DEFAULT_USERS="${MIRAI_SEED_DEFAULT_USERS:-1}"
export MIRAI_DEMO_MODE="${MIRAI_DEMO_MODE:-1}"
export MIRAI_FRONTEND_URL="${MIRAI_FRONTEND_URL:-https://carbon-mvp.mirai-dx-platform.com}"
export MIRAI_CORS_ORIGINS="${MIRAI_CORS_ORIGINS:-https://carbon-mvp.mirai-dx-platform.com,http://127.0.0.1:8021,http://localhost:8021}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/mvp_data/mirai_carbon_mvp.db}"
PORT="${MVP_PORT:-8021}"

mkdir -p "$ROOT/mvp_data"
python "$ROOT/seed_data.py"
python "$ROOT/scripts/seed_mvp_demo.py"
if ! python "$ROOT/scripts/verify_mvp_demo.py"; then
  echo "[start_mvp] WARNING: demo verification failed; starting anyway" >&2
fi

exec python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
