#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  secret="$(LC_ALL=C tr -dc 'A-Za-z0-9_@%+=:,.^-' < /dev/urandom | head -c 64 || true)"
  db_pass="$(LC_ALL=C tr -dc 'A-Za-z0-9_@%+=:,.^-' < /dev/urandom | head -c 32 || true)"
  if [ -n "$secret" ]; then
    sed -i "s/^DJANGO_SECRET_KEY=.*/DJANGO_SECRET_KEY=$secret/" .env
  fi
  if [ -n "$db_pass" ]; then
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$db_pass/" .env
  fi
fi

env_value() {
  local key="$1"
  local fallback="$2"
  local value=""
  value="$(grep -E "^${key}=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
  if [ -n "$value" ]; then
    printf '%s\n' "$value"
  else
    printf '%s\n' "$fallback"
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

append_csv_env_value() {
  local key="$1"
  local item="$2"
  local current=""
  current="$(env_value "$key" "")"
  case ",$current," in
    *",$item,"*) return 0 ;;
  esac
  if [ -n "$current" ]; then
    set_env_value "$key" "$current,$item"
  else
    set_env_value "$key" "$item"
  fi
}

proxy_port="$(env_value TRIVER_PROXY_HTTP_PORT 3080)"
if [ -z "$(env_value VITE_TRIVER_PUBLIC_URL "")" ]; then
  set_env_value VITE_TRIVER_PUBLIC_URL "http://localhost:${proxy_port}"
fi
if [ -z "$(env_value VITE_TRIVER_HTTP_ENDPOINT "")" ]; then
  set_env_value VITE_TRIVER_HTTP_ENDPOINT "localhost:${proxy_port}"
fi
append_csv_env_value DJANGO_CSRF_TRUSTED_ORIGINS "http://localhost:${proxy_port}"
append_csv_env_value DJANGO_CSRF_TRUSTED_ORIGINS "http://127.0.0.1:${proxy_port}"
append_csv_env_value DJANGO_CSRF_TRUSTED_ORIGINS "http://localhost"
append_csv_env_value DJANGO_CSRF_TRUSTED_ORIGINS "http://127.0.0.1"

mkdir -p \
  deploy/volumes/trive-In \
  deploy/volumes/trive-Up \
  deploy/volumes/trive-Out \
  deploy/volumes/trive-dump

touch \
  deploy/volumes/trive-In/.gitkeep \
  deploy/volumes/trive-Up/.gitkeep \
  deploy/volumes/trive-Out/.gitkeep \
  deploy/volumes/trive-dump/.gitkeep

echo "trueRiver local folders are ready."
echo "Put new media files in: $ROOT_DIR/deploy/volumes/trive-In"
echo "Start with: ./scripts/deploy-local.sh"
echo "Open: http://localhost:${proxy_port}"
