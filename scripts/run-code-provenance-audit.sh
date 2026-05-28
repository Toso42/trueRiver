#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${TRIVER_AUDIT_OUT_DIR:-$ROOT_DIR/docs/release-audit/current}"
EXPORT_DIR="${TRIVER_PROVENANCE_EXPORT_DIR:-/tmp/triver-public-provenance-audit}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

mkdir -p "$OUT_DIR"
rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"

git -C "$ROOT_DIR" archive --format=tar HEAD | tar -xf - -C "$EXPORT_DIR"

docker run --rm \
  -v "$EXPORT_DIR:/scan:ro" \
  -v "$OUT_DIR:/out" \
  node:20-alpine \
  sh -lc "cd /scan && npx --yes jscpd@4.2.3 backend frontend/source/srcnew apk/source/app/src/main deploy scripts --reporters json,markdown --output /out/jscpd --ignore '**/node_modules/**,**/frontend/package/build/**,**/package-lock.json' --min-lines 80 --min-tokens 120 && chown -R $HOST_UID:$HOST_GID /out/jscpd"

if [ "${TRIVER_RUN_SCANCODE:-0}" = "1" ]; then
  docker run --rm \
    -e PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}" \
    -e DEBIAN_FRONTEND=noninteractive \
    -v "$EXPORT_DIR:/scan:ro" \
    -v "$OUT_DIR:/out" \
    python:3.12-slim \
    sh -lc "apt-get update -qq && apt-get install -y -qq --no-install-recommends libgomp1 >/dev/null && pip install --no-cache-dir -q --root-user-action=ignore scancode-toolkit && scancode --license --copyright --info --classify --summary --processes ${TRIVER_SCANCODE_PROCESSES:-2} --json-pp /out/scancode-public-head.json /scan && chown $HOST_UID:$HOST_GID /out/scancode-public-head.json"
fi

echo "Code provenance audit complete."
echo "Export: $EXPORT_DIR"
echo "Reports: $OUT_DIR"
