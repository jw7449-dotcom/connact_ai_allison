#!/usr/bin/env bash
# Real Next/FastAPI integration tests against a disposable SQLite workspace.
# Optional invite run: E2E_AUTH_MODE=invite E2E_API_PORT=8002 E2E_FRONTEND_PORT=3102 E2E_NEXT_DIST_DIR=.next-e2e-auth ./scripts/test-e2e.sh tests/auth.spec.ts
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
if [ ! -x backend/.venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo 'Install backend/.venv and frontend/node_modules before running E2E.' >&2
  exit 1
fi
e2e_run_dir="$(mktemp -d "${TMPDIR:-/tmp}/connact-e2e.XXXXXX")"
export E2E_API_PORT="${E2E_API_PORT:-8001}"
export E2E_FRONTEND_PORT="${E2E_FRONTEND_PORT:-3101}"
export AUTH_MODE="${E2E_AUTH_MODE:-local}"
export AUTH_PROVIDER="${E2E_AUTH_PROVIDER:-password}" GOOGLE_CLIENT_ID='' GOOGLE_CLIENT_SECRET=''
if [ "$AUTH_PROVIDER" = "google" ]; then
  # Synthetic credentials exercise redirects/state only; never complete a Google exchange.
  export GOOGLE_CLIENT_ID='isolated-e2e.apps.googleusercontent.com'
  export GOOGLE_CLIENT_SECRET='isolated-e2e-not-a-real-secret'
fi
export NEXT_DIST_DIR="${E2E_NEXT_DIST_DIR:-.next-e2e}"
export DATABASE_URL="sqlite:///$e2e_run_dir/workspace.db"
export UPLOAD_DIR="$e2e_run_dir/uploads"
export WORKSPACE_ID="isolated-e2e"
export PEOPLE_MODE=mock AI_MODE=mock PUBLIC_SEARCH_MODE=mock
export APOLLO_API_KEY='' SERPAPI_API_KEY='' AI_API_KEY='' APIFY_API_KEY=''
export OPENAI_API_KEY='' DEEPSEEK_API_KEY='' GEMINI_API_KEY='' ANTHROPIC_API_KEY='' DASHSCOPE_API_KEY=''
export AI_DEFAULT_MODEL='' AI_PROVIDERS='[]'
export AI_PROVIDER=mock AI_MODEL=qwen-plus AI_MODELS=qwen-plus,qwen-turbo,qwen-max
export PUBLIC_ORIGIN="http://127.0.0.1:$E2E_FRONTEND_PORT"
export BACKEND_URL="http://127.0.0.1:$E2E_API_PORT"
export E2E_URL="$PUBLIC_ORIGIN"
export E2E_AUTH_MODE="$AUTH_MODE"
export E2E_INVITATION='isolated-test-invitation-2026'
export E2E_SECOND_INVITATION='isolated-second-invitation-2026'
export E2E_TEST_EMAIL='browser-e2e@example.test'
export E2E_SECOND_EMAIL='other-e2e@example.test'
# Refuse to attach to an existing service or reuse the main Next output.
case "$NEXT_DIST_DIR" in .next-e2e*) ;; *) echo 'E2E_NEXT_DIST_DIR must begin with .next-e2e' >&2; exit 1;; esac
backend/.venv/bin/python - <<'PY'
import os, socket
for key in ('E2E_API_PORT', 'E2E_FRONTEND_PORT'):
    with socket.socket() as probe:
        try: probe.bind(('127.0.0.1', int(os.environ[key])))
        except OSError: raise SystemExit(f'{key} is already in use. Choose a free isolated port.')
PY
(cd backend && .venv/bin/python - <<'PY'
import os
from datetime import datetime, timedelta, timezone
from app.main import app
from app.db import Base, engine, Session
from app.auth_models import Invitation
from app.routers.auth import digest
Base.metadata.create_all(engine)
if os.environ['AUTH_MODE'] == 'invite':
    with Session() as db:
        for token, email in ((os.environ['E2E_INVITATION'], os.environ['E2E_TEST_EMAIL']), (os.environ['E2E_SECOND_INVITATION'], os.environ['E2E_SECOND_EMAIL'])):
            db.add(Invitation(token_hash=digest(token), email=email, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
if os.environ['AUTH_MODE'] == 'open':
    from app.bootstrap_admin import bootstrap_admin
    from app.config import settings
    from app.routers.auth import password_hash
    settings.bootstrap_admin_password_hash = password_hash('browser-admin-test-only')
    bootstrap_admin()
PY
)
cp frontend/tsconfig.json "$e2e_run_dir/tsconfig.before.json"
cp frontend/next-env.d.ts "$e2e_run_dir/next-env.before.d.ts"
e2e_pids=()
cleanup() {
  for e2e_pid in "${e2e_pids[@]}"; do kill "$e2e_pid" 2>/dev/null || true; done
  for e2e_pid in "${e2e_pids[@]}"; do wait "$e2e_pid" 2>/dev/null || true; done
  # Next updates generated type references even with an isolated distDir.
  # Restore only the changes this run owns; preserve concurrent unrelated edits.
  backend/.venv/bin/python - "$e2e_run_dir" "$NEXT_DIST_DIR" <<'PY_RESTORE'
import json, sys
from pathlib import Path
run_dir, dist = Path(sys.argv[1]), sys.argv[2]
config_path = Path('frontend/tsconfig.json')
before_text = (run_dir / 'tsconfig.before.json').read_text()
before, current = json.loads(before_text), json.loads(config_path.read_text())
added = {f'{dist}/types/**/*.ts', f'{dist}/dev/types/**/*.ts'} - set(before.get('include', []))
current['include'] = [item for item in current.get('include', []) if item not in added]
if current == before:
    config_path.write_text(before_text)
else:
    config_path.write_text(json.dumps(current, indent=2) + '\n')
types_path = Path('frontend/next-env.d.ts')
if f'./{dist}/' in types_path.read_text():
    types_path.write_text((run_dir / 'next-env.before.d.ts').read_text())
PY_RESTORE
  echo "Isolated E2E logs and test database: $e2e_run_dir"
}
trap cleanup EXIT INT TERM
(cd backend && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$E2E_API_PORT") > "$e2e_run_dir/backend.log" 2>&1 &
e2e_pids+=("$!")
(cd frontend && exec node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port "$E2E_FRONTEND_PORT") > "$e2e_run_dir/frontend.log" 2>&1 &
e2e_pids+=("$!")
e2e_ready=0
for e2e_attempt in $(seq 1 60); do
  if curl --fail --silent --max-time 3 "$E2E_URL/api/health" >/dev/null; then e2e_ready=1; break; fi
  sleep 1
done
if [ "$e2e_ready" != 1 ]; then
  cat "$e2e_run_dir/backend.log" "$e2e_run_dir/frontend.log" >&2
  exit 1
fi
if [ "$#" -eq 0 ]; then set -- tests/workflow.spec.ts tests/writing.spec.ts; fi
(cd frontend && exec node node_modules/@playwright/test/cli.js test "$@")
