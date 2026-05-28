#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${TRIVER_LOCAL_DIR:-$ROOT_DIR/../triver-local}"
REF="${1:-}"

cd "$ROOT_DIR"

if [ -d .git ]; then
  git fetch --tags origin
  if [ -n "$REF" ]; then
    git checkout -f "$REF"
  else
    git pull --ff-only
  fi
fi

if [ ! -f "${TRIVER_ENV_FILE:-$LOCAL_DIR/.env}" ] && [ ! -f .env ]; then
  ./scripts/pre-compose-up.sh
fi

if [ "${TRIVER_REBUILD_FRONTEND:-0}" = "1" ]; then
  ./scripts/build-frontend.sh
fi

if [ "${TRIVER_DEPLOY_ALLOW_ACTIVE_JOBS:-0}" != "1" ]; then
  backend_container="$(./scripts/compose-local.sh ps -q triver-backend 2>/dev/null || true)"
  if [ -n "$backend_container" ] && [ "$(docker inspect -f '{{.State.Running}}' "$backend_container" 2>/dev/null || true)" = "true" ]; then
    active_jobs="$(
      ./scripts/compose-local.sh exec -T triver-backend python manage.py shell -c "from apps.library.models import LibraryDigestJob, LibraryScanJob; scan=LibraryScanJob.objects.filter(status__in=['pending','discovering','processing']).count(); digest=LibraryDigestJob.objects.filter(status__in=['pending','running']).count(); print(f'{scan} scan job(s), {digest} trive-up job(s)' if scan or digest else '')" 2>/dev/null || true
    )"
    active_jobs="$(printf '%s' "$active_jobs" | tail -n 1)"
    if [ -n "$active_jobs" ]; then
      cat >&2 <<EOF
Active trive-IO jobs are still running: $active_jobs

Deployment would restart the worker and may leave in-flight work waiting for
broker recovery. Wait for the jobs to finish, or rerun with:

  TRIVER_DEPLOY_ALLOW_ACTIVE_JOBS=1 ./scripts/deploy-local.sh
EOF
      exit 1
    fi
  fi
fi

if [ ! -f frontend/package/build/index.html ]; then
  cat >&2 <<'EOF'
frontend/package/build/index.html is missing.

Git checkouts and source archives should include a prebuilt frontend.
Either restore the committed build files or rebuild the web frontend explicitly:

  ./scripts/build-frontend.sh

Then rerun:

  ./scripts/deploy-local.sh
EOF
  exit 1
fi

./scripts/compose-local.sh rm -sf triver-proxy >/dev/null 2>&1 || true
./scripts/compose-local.sh up -d --build --remove-orphans
