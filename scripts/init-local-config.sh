#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUESTED_LOCAL_DIR="${TRIVER_LOCAL_DIR:-$ROOT_DIR/../triver-local}"

mkdir -p "$REQUESTED_LOCAL_DIR"
LOCAL_DIR="$(cd "$REQUESTED_LOCAL_DIR" && pwd)"
ENV_FILE="$LOCAL_DIR/.env"
COMPOSE_FILE="$LOCAL_DIR/docker-compose.local.yml"

copy_if_missing() {
  local source="$1"
  local target="$2"
  if [ ! -f "$target" ]; then
    cp "$source" "$target"
  fi
}

env_value() {
  local key="$1"
  local fallback="${2:-}"
  local value=""
  value="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
  if [ -n "$value" ]; then
    printf '%s\n' "$value"
  else
    printf '%s\n' "$fallback"
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

random_value() {
  local length="$1"
  LC_ALL=C tr -dc 'A-Za-z0-9_@%+=:,.^-' < /dev/urandom | head -c "$length" || true
}

seed_secret() {
  local key="$1"
  local length="$2"
  local current=""
  current="$(env_value "$key")"
  if [ -z "$current" ] || [ "$current" = "change-me-before-use" ]; then
    set_env_value "$key" "$(random_value "$length")"
  fi
}

mkdir_from_env() {
  local key="$1"
  local path=""
  path="$(env_value "$key")"
  if [ -n "$path" ]; then
    mkdir -p "$path"
  fi
}

seed_host_path() {
  local key="$1"
  local leaf="$2"
  local current=""
  current="$(env_value "$key")"
  if [ -z "$current" ] || [[ "$current" == /srv/trueriver/* ]]; then
    set_env_value "$key" "$LOCAL_DIR/volumes/$leaf"
  fi
}

copy_if_missing "$ROOT_DIR/deploy/examples/local.env.example" "$ENV_FILE"
copy_if_missing "$ROOT_DIR/deploy/examples/docker-compose.local.yml" "$COMPOSE_FILE"

seed_secret DJANGO_SECRET_KEY 64
seed_secret POSTGRES_PASSWORD 32

seed_host_path TRIVER_POSTGRES_HOST_PATH postgres
seed_host_path TRIVER_VALKEY_HOST_PATH valkey
seed_host_path TRIVER_CLAMAV_HOST_PATH clamav
seed_host_path TRIVER_WIREGUARD_HOST_PATH wireguard
seed_host_path TRIVER_STORAGE_HOST_PATH storage
set_env_value TRIVER_ALLOW_CROSS_DEVICE_MOVES "$(env_value TRIVER_ALLOW_CROSS_DEVICE_MOVES false)"

proxy_port="$(env_value TRIVER_PROXY_HTTP_PORT 3080)"
if [ -z "$(env_value VITE_TRIVER_PUBLIC_URL)" ]; then
  set_env_value VITE_TRIVER_PUBLIC_URL "http://localhost:${proxy_port}"
fi
if [ -z "$(env_value VITE_TRIVER_HTTP_ENDPOINT)" ]; then
  set_env_value VITE_TRIVER_HTTP_ENDPOINT "localhost:${proxy_port}"
fi

mkdir_from_env TRIVER_POSTGRES_HOST_PATH
mkdir_from_env TRIVER_VALKEY_HOST_PATH
mkdir_from_env TRIVER_CLAMAV_HOST_PATH
mkdir_from_env TRIVER_WIREGUARD_HOST_PATH
mkdir_from_env TRIVER_STORAGE_HOST_PATH
storage_path="$(env_value TRIVER_STORAGE_HOST_PATH)"
if [ -n "$storage_path" ]; then
  mkdir -p "$storage_path/trive-In" "$storage_path/trive-Up" "$storage_path/trive-Out" "$storage_path/trive-dump"
fi

cat <<EOF
trueRiver local config is ready in:
  $LOCAL_DIR

Review host names, public URL and storage paths in:
  $ENV_FILE

Then deploy with:
  TRIVER_LOCAL_DIR="$LOCAL_DIR" ./scripts/deploy-local.sh
EOF
