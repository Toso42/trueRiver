#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

git diff --check

"$ROOT_DIR/scripts/compose-local.sh" run --rm --no-deps triver-backend \
  python -m compileall -q apps triver utils

"$ROOT_DIR/scripts/test-api.sh" "$@"
