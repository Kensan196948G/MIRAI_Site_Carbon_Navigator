#!/usr/bin/env bash
# Wrapper for cron: loads .env (without printing secrets) and runs backup.
set -a
if [ -f "$(dirname "$0")/../.env" ]; then
  # shellcheck disable=SC1091
  . "$(dirname "$0")/../.env"
fi
set +a
exec "$(dirname "$0")/backup.sh"
