#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
THREADS="${THREADS:-8}"

exec gunicorn \
  --workers 1 \
  --threads "$THREADS" \
  --bind "${HOST}:${PORT}" \
  --timeout 600 \
  --access-logfile - \
  --error-logfile - \
  web.app:app
