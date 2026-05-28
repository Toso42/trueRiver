#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="${MIBOX_FTP_HOST:-}"
PORT="${MIBOX_FTP_PORT:-8290}"
USER_NAME="${MIBOX_FTP_USER:-}"
REMOTE_DIR="${MIBOX_FTP_REMOTE_DIR:-device/Download}"
APK_PATH="${1:-$SCRIPT_DIR/app/build/outputs/apk/debug/app-debug.apk}"
DEFAULT_REMOTE_NAME="$(awk -F"'" '/versionName/ {print "trueriver-" $2 ".apk"; exit}' "$SCRIPT_DIR/app/build.gradle" 2>/dev/null || true)"
REMOTE_NAME="${MIBOX_FTP_REMOTE_NAME:-${DEFAULT_REMOTE_NAME:-$(basename "$APK_PATH")}}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

if [[ -z "$HOST" || -z "$USER_NAME" ]]; then
  echo "Set MIBOX_FTP_HOST and MIBOX_FTP_USER before uploading." >&2
  exit 1
fi

if [[ ! -f "$APK_PATH" ]]; then
  echo "APK not found: $APK_PATH" >&2
  exit 1
fi

FTP_PASSWORD="${MIBOX_FTP_PASSWORD:-}"
if [[ -z "$FTP_PASSWORD" ]]; then
  read -r -s -p "Mi Box FTP password for ${USER_NAME}@${HOST}:${PORT}: " FTP_PASSWORD
  echo
fi

if [[ -z "$FTP_PASSWORD" ]]; then
  echo "No password provided." >&2
  exit 1
fi

REMOTE_URL="ftp://${HOST}:${PORT}/${REMOTE_DIR}/${REMOTE_NAME}"

echo "Uploading:"
echo "  local : $APK_PATH"
echo "  remote: $REMOTE_URL"

curl --fail --show-error --ftp-port - --disable-eprt \
  --user "${USER_NAME}:${FTP_PASSWORD}" \
  -T "$APK_PATH" \
  "$REMOTE_URL"

echo "Upload complete."
