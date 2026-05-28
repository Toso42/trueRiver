#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REF="${1:-${TRIVER_UPDATE_REF:-origin/main}}"
REMOTE="${TRIVER_GIT_REMOTE:-}"
SKIP_COMPOSE="${TRIVER_UPDATE_SKIP_COMPOSE:-0}"
LOCAL_DIR="${TRIVER_LOCAL_DIR:-$ROOT_DIR/../triver-local}"
ENV_FILE="${TRIVER_ENV_FILE:-$LOCAL_DIR/.env}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required for trueRiver server updates." >&2
  exit 1
fi

if [ "$SKIP_COMPOSE" != "1" ] && ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for trueRiver server updates." >&2
  exit 1
fi

if [ -d .git ]; then
  if [ -n "$(git status --porcelain --untracked-files=no)" ] && [ "${TRIVER_UPDATE_ALLOW_DIRTY:-0}" != "1" ]; then
    echo "tracked files have local changes; refusing to update." >&2
    echo "Commit/revert them, or set TRIVER_UPDATE_ALLOW_DIRTY=1 if you know why." >&2
    exit 1
  fi
else
  if [ -z "$REMOTE" ]; then
    echo "this install was unpacked from an archive and has no .git directory." >&2
    echo "set TRIVER_GIT_REMOTE to the repository URL, then rerun this script." >&2
    echo "example: TRIVER_GIT_REMOTE=https://example.org/owner/trueriver.git ./scripts/update-server.sh v0.1.0-techdemo.3" >&2
    exit 1
  fi
  git init
  git remote add origin "$REMOTE"
fi

if [ -n "$REMOTE" ]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE"
  else
    git remote add origin "$REMOTE"
  fi
fi

echo "Fetching trueRiver updates..."
git fetch --tags origin

if [ "$REF" = "main" ]; then
  REF="origin/main"
fi

echo "Switching source tree to $REF..."
git checkout -f -B trueriver-install "$REF"

if [ ! -f "$ENV_FILE" ] && [ ! -f .env ]; then
  echo "Preparing local folders and environment..."
  ./scripts/pre-compose-up.sh
else
  echo "Using existing local configuration."
fi

if [ "$SKIP_COMPOSE" = "1" ]; then
  echo "TRIVER_UPDATE_SKIP_COMPOSE=1; source tree updated without restarting Docker."
  exit 0
fi

echo "Pulling upstream service images..."
./scripts/compose-local.sh pull

if [ "${TRIVER_REBUILD_FRONTEND:-0}" = "1" ]; then
  echo "Rebuilding web frontend..."
  ./scripts/build-frontend.sh
fi

if [ ! -f frontend/package/build/index.html ]; then
  cat >&2 <<'EOF'
frontend/package/build/index.html is missing.

Git checkouts and source archives should include a prebuilt frontend.
Either restore the committed build files or rebuild the web frontend explicitly:

  ./scripts/build-frontend.sh
EOF
  exit 1
fi

echo "Forcing proxy refresh..."
./scripts/compose-local.sh rm -sf triver-proxy >/dev/null 2>&1 || true

echo "Rebuilding and restarting trueRiver..."
./scripts/compose-local.sh up -d --build --remove-orphans

echo "trueRiver updated to $(git rev-parse --short HEAD)."
