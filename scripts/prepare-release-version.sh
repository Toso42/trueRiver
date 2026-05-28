#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/version.sh"

UPDATE_ANDROID=0
ANDROID_VERSION_CODE="${TRIVER_ANDROID_VERSION_CODE:-}"
PRERELEASE_LABEL="${TRIVER_PRERELEASE_LABEL:-techdemo}"

usage() {
  cat >&2 <<'EOF'
usage: scripts/prepare-release-version.sh [options] <version|major|minor|patch|prerelease>

Examples:
  scripts/prepare-release-version.sh prerelease
  scripts/prepare-release-version.sh patch
  scripts/prepare-release-version.sh v0.1.0-techdemo.6

Options:
  --android                 also update Android versionName/versionCode
  --no-android              leave Android versionName/versionCode unchanged
  --android-version-code N  set Android versionCode explicitly and update Android
  --prerelease-label NAME   prerelease label for "prerelease" bumps
EOF
}

ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --android)
      UPDATE_ANDROID=1
      ;;
    --no-android)
      UPDATE_ANDROID=0
      ;;
    --android-version-code)
      shift
      if [ "$#" -eq 0 ]; then
        echo "--android-version-code requires a value" >&2
        exit 1
      fi
      ANDROID_VERSION_CODE="$1"
      UPDATE_ANDROID=1
      ;;
    --prerelease-label)
      shift
      if [ "$#" -eq 0 ]; then
        echo "--prerelease-label requires a value" >&2
        exit 1
      fi
      PRERELEASE_LABEL="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      ARGS+=("$1")
      ;;
  esac
  shift
done

if [ "${#ARGS[@]}" -ne 1 ]; then
  usage
  exit 1
fi

REQUESTED="${ARGS[0]}"
CURRENT="$(triver_version_read "$ROOT_DIR/VERSION" 2>/dev/null || git -C "$ROOT_DIR" describe --tags --abbrev=0 2>/dev/null || printf 'v0.1.0-%s.0\n' "$PRERELEASE_LABEL")"

NEW_VERSION="$(python3 - "$CURRENT" "$REQUESTED" "$PRERELEASE_LABEL" <<'PY'
import re
import sys

current, requested, prerelease_label = sys.argv[1:4]
semver = re.compile(
    r"^v?(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def parse(version):
    match = semver.match(version)
    if not match:
        raise SystemExit(f"not a semver release: {version}")
    return {
        "major": int(match.group("major")),
        "minor": int(match.group("minor")),
        "patch": int(match.group("patch")),
        "pre": match.group("pre") or "",
    }


def render(parts, pre=""):
    value = f"{parts['major']}.{parts['minor']}.{parts['patch']}"
    if pre:
        value += f"-{pre}"
    return f"v{value}"


if requested in {"major", "minor", "patch", "prerelease"}:
    parts = parse(current)
    if requested == "major":
        parts["major"] += 1
        parts["minor"] = 0
        parts["patch"] = 0
        print(render(parts))
    elif requested == "minor":
        parts["minor"] += 1
        parts["patch"] = 0
        print(render(parts))
    elif requested == "patch":
        parts["patch"] += 1
        print(render(parts))
    else:
        pre = parts["pre"]
        ids = pre.split(".") if pre else []
        if len(ids) >= 2 and ids[0] == prerelease_label and ids[-1].isdigit():
            ids[-1] = str(int(ids[-1]) + 1)
        else:
            ids = [prerelease_label, "1"]
        print(render(parts, ".".join(ids)))
else:
    parse(requested)
    print("v" + requested[1:] if requested.startswith("v") else "v" + requested)
PY
)"

if ! triver_version_is_semver "$NEW_VERSION"; then
  echo "invalid release version: $NEW_VERSION" >&2
  exit 1
fi

VERSION_CORE="$(triver_version_strip_v "$NEW_VERSION")"

if [ -n "$ANDROID_VERSION_CODE" ] && ! [[ "$ANDROID_VERSION_CODE" =~ ^[0-9]+$ ]]; then
  echo "Android versionCode must be an integer: $ANDROID_VERSION_CODE" >&2
  exit 1
fi

python3 - "$ROOT_DIR" "$NEW_VERSION" "$VERSION_CORE" "$UPDATE_ANDROID" "$ANDROID_VERSION_CODE" <<'PY'
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

root = Path(sys.argv[1])
tag_version = sys.argv[2]
core_version = sys.argv[3]
update_android = sys.argv[4] == "1"
requested_android_code = sys.argv[5]

(root / "VERSION").write_text(f"{tag_version}\n", encoding="utf-8")

for relative in ("frontend/source/package.json", "frontend/source/package-lock.json"):
    path = root / relative
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = core_version
    if relative.endswith("package-lock.json"):
        data.setdefault("packages", {}).setdefault("", {})["version"] = core_version
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

if update_android:
    gradle_path = root / "apk/source/app/build.gradle"
    text = gradle_path.read_text(encoding="utf-8")
    code_match = re.search(r"versionCode\s+([0-9]+)", text)
    name_match = re.search(r"versionName\s+'([^']+)'", text)
    if not code_match or not name_match:
        raise SystemExit("could not read Android versionCode/versionName")

    current_code = int(code_match.group(1))
    current_name = name_match.group(1)
    if requested_android_code:
        next_code = int(requested_android_code)
    else:
        next_code = current_code if current_name == core_version else current_code + 1

    wrapper_version = quote(core_version, safe=".-")
    replacements = [
        (r"versionCode\s+[0-9]+", f"versionCode {next_code}"),
        (r"versionName\s+'[^']+'", f"versionName '{core_version}'"),
        (
            r"(buildConfigField 'String', 'TV_START_PATH', '\"/tv/video\?tv_shell=1&wrapper=)[^\"']+(\")",
            rf"\g<1>{wrapper_version}\g<2>",
        ),
        (
            r"(buildConfigField 'String', 'TV_USER_AGENT_SUFFIX', '\"trueRiverTvShell/)[^\"']+(\")",
            rf"\g<1>{core_version}\g<2>",
        ),
    ]
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise SystemExit(f"could not update Android Gradle pattern: {pattern}")
    gradle_path.write_text(text, encoding="utf-8")
PY

echo "Prepared trueRiver release $NEW_VERSION"
echo "Updated VERSION and frontend package metadata."
if [ "$UPDATE_ANDROID" = "1" ]; then
  echo "Updated Android versionName and versionCode."
fi
