#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
if [ ! -d backend/.venv ]; then "${PYTHON:-python3}" -m venv backend/.venv; fi
backend/.venv/bin/pip install -q -r backend/requirements.txt
if [ ! -d frontend/node_modules ]; then (cd frontend && npm ci); fi
mkdir -p data
meridian_pids=()
cleanup() { for p in "${meridian_pids[@]}"; do kill "$p" 2>/dev/null || true; done; wait || true; }
trap cleanup EXIT INT TERM
if [ "${LOCAL_POSTGRES:-1}" = "1" ]; then
  node frontend/local-postgres.mjs > data/postgres.log 2>&1 &
  meridian_pids+=("$!")
fi
# Wait for the configured database, not for an arbitrary fixed delay.
for i in $(seq 1 30); do
  if (cd backend && .venv/bin/python -c 'from app.db import engine; c=engine.connect(); c.close()') >/dev/null 2>&1; then break; fi
  if [ "$i" = "30" ]; then echo 'Database unavailable. Check data/postgres.log or DATABASE_URL.'; exit 1; fi
  sleep 1
done
(cd backend && .venv/bin/alembic upgrade head)
if [ "${SEED_DEMO:-0}" = "1" ]; then (cd backend && .venv/bin/python -m app.seed); fi
(cd backend && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) &
meridian_pids+=("$!")
(cd frontend && exec node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3100) &
meridian_pids+=("$!")
echo 'Connact.ai: http://127.0.0.1:3100 | API: http://127.0.0.1:8000/docs'
echo 'Press Ctrl+C to stop this local stack. Data stays in data/.'
wait
