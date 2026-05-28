#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${TRIVER_LOCAL_DIR:-$ROOT_DIR/../triver-local}"

env_file="${TRIVER_ENV_FILE:-}"
if [ -z "$env_file" ]; then
  if [ -f "$LOCAL_DIR/.env" ]; then
    env_file="$LOCAL_DIR/.env"
  else
    env_file="$ROOT_DIR/.env"
  fi
fi

override_file="${TRIVER_COMPOSE_OVERRIDE:-}"
if [ -z "$override_file" ]; then
  if [ -f "$LOCAL_DIR/docker-compose.local.yml" ]; then
    override_file="$LOCAL_DIR/docker-compose.local.yml"
  elif [ -f "$ROOT_DIR/docker-compose.override.yml" ]; then
    override_file="$ROOT_DIR/docker-compose.override.yml"
  fi
fi

env_file_value() {
  local key="$1"
  local file="$2"
  if [ -f "$file" ]; then
    grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- || true
  fi
}

extra_compose_file="${TRIVER_COMPOSE_EXTRA:-}"
if [ -z "$extra_compose_file" ]; then
  extra_compose_file="$(env_file_value TRIVER_COMPOSE_EXTRA "$env_file")"
fi

project_name="${TRIVER_COMPOSE_PROJECT_NAME:-${COMPOSE_PROJECT_NAME:-}}"
if [ -z "$project_name" ]; then
  project_name="$(env_file_value TRIVER_COMPOSE_PROJECT_NAME "$env_file")"
fi
if [ -z "$project_name" ]; then
  project_name="$(env_file_value COMPOSE_PROJECT_NAME "$env_file")"
fi

compose_args=()
if [ -f "$env_file" ]; then
  export TRIVER_SERVICE_ENV_FILE="$env_file"
  compose_args+=(--env-file "$env_file")
fi
if [ -n "$project_name" ]; then
  compose_args+=(-p "$project_name")
fi

compose_args+=(-f "$ROOT_DIR/docker-compose.yml")
if [ -n "$override_file" ]; then
  IFS=':' read -r -a override_files <<< "$override_file"
  for file in "${override_files[@]}"; do
    compose_args+=(-f "$file")
  done
fi
if [ -n "$extra_compose_file" ]; then
  IFS=':' read -r -a extra_compose_files <<< "$extra_compose_file"
  for file in "${extra_compose_files[@]}"; do
    compose_args+=(-f "$file")
  done
fi

cd "$ROOT_DIR"
exec docker compose "${compose_args[@]}" "$@"
