#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${TRIVER_LOCAL_DIR:-$ROOT_DIR/../triver-local}"
BUILD_COMPOSE_FILE="$ROOT_DIR/deploy/compose/frontend-build.yml"

if [ ! -f "$BUILD_COMPOSE_FILE" ]; then
  echo "missing frontend build compose file: $BUILD_COMPOSE_FILE" >&2
  exit 1
fi

if [ -z "${TRIVER_ENV_FILE:-}" ] && [ ! -f "$LOCAL_DIR/.env" ] && [ ! -f "$ROOT_DIR/.env" ]; then
  export TRIVER_ENV_FILE="$ROOT_DIR/.env.example"
fi

if [ -n "${TRIVER_COMPOSE_EXTRA:-}" ]; then
  export TRIVER_COMPOSE_EXTRA="${TRIVER_COMPOSE_EXTRA}:$BUILD_COMPOSE_FILE"
else
  export TRIVER_COMPOSE_EXTRA="$BUILD_COMPOSE_FILE"
fi

"$ROOT_DIR/scripts/compose-local.sh" run --rm triver-frontend-build

private_hits_file="$(mktemp)"
frontend_private_pattern="${TRIVER_FRONTEND_PRIVATE_PATTERN:-127\.0\.0\.1|localhost|192\.168\.|10\.44\.0\.|ssh://git@|triver-live-proxy|triver-backend:3000|VITE_TRIVER_(BACKEND_UPSTREAM|VPN_ENDPOINT|VPN_WEB_URL|PROXY_VPN_IP|PROXY_ALLOWED_PORTS)|Reverse proxy|VPN edge|Deployment controls|Server Settings}"
if grep -RInE "$frontend_private_pattern" "$ROOT_DIR/frontend/package/build" >"$private_hits_file"; then
  cat "$private_hits_file" >&2
  rm -f "$private_hits_file"
  echo "frontend build contains private/local deployment values" >&2
  exit 1
fi
rm -f "$private_hits_file"
