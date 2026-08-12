#!/usr/bin/env bash
# Container entrypoint: validates production settings, seeds the database,
# then starts uvicorn. Fails closed instead of booting with insecure defaults.
set -euo pipefail

if [ "${MIRAI_ENV:-development}" = "production" ]; then
  if [ -z "${MIRAI_SECRET_KEY:-}" ] || [ "${MIRAI_SECRET_KEY}" = "change-me-in-production" ]; then
    echo "FATAL: MIRAI_SECRET_KEY must be set to a real secret in production" >&2
    exit 1
  fi
fi

python seed_data.py

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${UVICORN_WORKERS:-2}"
