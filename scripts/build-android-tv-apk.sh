#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APK_DIR="$ROOT_DIR/apk/source"
OUT_DIR="$ROOT_DIR/apk/package"
IMAGE="${TRIVER_ANDROID_BUILDER_IMAGE:-ghcr.io/cirruslabs/android-sdk@sha256:1c2e7e9c4490dbc1f85364556aa08e550945e6dffb29baab86d5fe2c7be0773a}"
MODE="${1:-release}"
EXPECTED_RELEASE_CERT_SHA256="${TRIVER_ANDROID_EXPECTED_CERT_SHA256:-488e9cc9dc3c0d0964c908fbdeb3e56846aa7cb24526abec679c2d3d66216acc}"

if [ "$MODE" != "release" ] && [ "$MODE" != "debug" ]; then
  echo "usage: $0 [release|debug]" >&2
  exit 1
fi

VERSION="$(awk -F"'" '/versionName/ {print $2; exit}' "$APK_DIR/app/build.gradle")"
if [ -z "$VERSION" ]; then
  echo "could not read Android versionName" >&2
  exit 1
fi

if [ "$MODE" = "release" ] && [ "${TRIVER_ANDROID_UNSIGNED_RELEASE:-0}" != "1" ]; then
  for name in TRIVER_ANDROID_KEYSTORE TRIVER_ANDROID_KEYSTORE_PASSWORD TRIVER_ANDROID_KEY_ALIAS TRIVER_ANDROID_KEY_PASSWORD; do
    if [ -z "${!name:-}" ]; then
      echo "missing $name for signed release build" >&2
      echo "set TRIVER_ANDROID_UNSIGNED_RELEASE=1 only for local unsigned verification builds" >&2
      exit 1
    fi
  done
  if [ ! -f "$APK_DIR/$TRIVER_ANDROID_KEYSTORE" ]; then
    echo "keystore not found under apk/source: $TRIVER_ANDROID_KEYSTORE" >&2
    exit 1
  fi
fi

mkdir -p "$OUT_DIR"

TASK="assembleRelease"
if [ "$MODE" = "debug" ]; then
  TASK="assembleDebug"
fi

docker run --rm \
  -v "$APK_DIR:/workspace" \
  -w /workspace \
  -e GRADLE_USER_HOME=/tmp/gradle-home \
  -e TRIVER_ANDROID_KEYSTORE="${TRIVER_ANDROID_KEYSTORE:-}" \
  -e TRIVER_ANDROID_KEYSTORE_PASSWORD="${TRIVER_ANDROID_KEYSTORE_PASSWORD:-}" \
  -e TRIVER_ANDROID_KEY_ALIAS="${TRIVER_ANDROID_KEY_ALIAS:-}" \
  -e TRIVER_ANDROID_KEY_PASSWORD="${TRIVER_ANDROID_KEY_PASSWORD:-}" \
  "$IMAGE" \
  ./gradlew --no-daemon clean "$TASK"

if [ "$MODE" = "debug" ]; then
  APK_SOURCE="$APK_DIR/app/build/outputs/apk/debug/app-debug.apk"
  APK_NAME="trueriver-tv-$VERSION-debug.apk"
else
  APK_SOURCE="$APK_DIR/app/build/outputs/apk/release/app-release.apk"
  APK_NAME="trueriver-tv-$VERSION.apk"
  if [ ! -f "$APK_SOURCE" ]; then
    APK_SOURCE="$APK_DIR/app/build/outputs/apk/release/app-release-unsigned.apk"
    APK_NAME="trueriver-tv-$VERSION-unsigned.apk"
  fi
fi

if [ ! -f "$APK_SOURCE" ]; then
  echo "APK output not found for $MODE build" >&2
  exit 1
fi

if [ "$MODE" = "release" ] && [ "$APK_NAME" = "trueriver-tv-$VERSION.apk" ] && [ -n "$EXPECTED_RELEASE_CERT_SHA256" ]; then
  APK_SOURCE_IN_CONTAINER="${APK_SOURCE#$APK_DIR/}"
  docker run --rm \
    -v "$APK_DIR:/workspace:ro" \
    -w /workspace \
    "$IMAGE" \
    bash -lc '
      set -euo pipefail
      apk_path="$1"
      expected="$(printf "%s" "$2" | tr "[:upper:]" "[:lower:]" | tr -d ":[:space:]")"
      actual="$("$ANDROID_HOME/build-tools/34.0.0/apksigner" verify --print-certs "$apk_path" | awk -F": " "/Signer #1 certificate SHA-256 digest/ {print tolower(\$2); exit}")"
      actual="$(printf "%s" "$actual" | tr -d ":[:space:]")"
      if [ -z "$actual" ]; then
        echo "could not read APK signer certificate" >&2
        exit 1
      fi
      if [ "$actual" != "$expected" ]; then
        echo "release APK signer certificate mismatch" >&2
        echo "expected: $expected" >&2
        echo "actual:   $actual" >&2
        exit 1
      fi
    ' _ "$APK_SOURCE_IN_CONTAINER" "$EXPECTED_RELEASE_CERT_SHA256"
fi

cp "$APK_SOURCE" "$OUT_DIR/$APK_NAME"
(
  cd "$OUT_DIR"
  sha256sum "$APK_NAME" > "$APK_NAME.sha256"
)

echo "wrote $OUT_DIR/$APK_NAME"
