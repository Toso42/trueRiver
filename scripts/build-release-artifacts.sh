#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/version.sh"

VERSION="${1:-${TRIVER_RELEASE_VERSION:-}}"
if [ -z "$VERSION" ]; then
  VERSION="$(triver_version_read "$ROOT_DIR/VERSION" 2>/dev/null || true)"
fi
if [ -z "$VERSION" ]; then
  echo "usage: $0 [version]" >&2
  echo "example: $0 v0.1.0" >&2
  echo "when omitted, the version is read from ./VERSION" >&2
  exit 1
fi

if triver_version_is_semver "$VERSION"; then
  VERSION="$(triver_version_with_v "$VERSION")"
elif [ "${TRIVER_ALLOW_NON_SEMVER_RELEASE:-0}" != "1" ]; then
  echo "release version must be semver, for example v0.1.0 or v0.1.0-techdemo.5: $VERSION" >&2
  echo "set TRIVER_ALLOW_NON_SEMVER_RELEASE=1 only for local smoke tests" >&2
  exit 1
fi

OUT_DIR="${TRIVER_RELEASE_DIR:-$ROOT_DIR/release/artifacts/$VERSION}"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

COMMIT="$(git rev-parse HEAD)"
TAG="$(git describe --tags --exact-match 2>/dev/null || true)"
REMOTE_URL="$(git config --get remote.origin.url || true)"
REMOTE_WEB_URL="$REMOTE_URL"
if [[ "$REMOTE_WEB_URL" == git@*:* ]]; then
  REMOTE_WEB_URL="https://${REMOTE_WEB_URL#git@}"
  REMOTE_WEB_URL="${REMOTE_WEB_URL/:/\/}"
elif [[ "$REMOTE_WEB_URL" == ssh://git@* ]]; then
  REMOTE_WEB_URL="https://${REMOTE_WEB_URL#ssh://git@}"
fi
REMOTE_WEB_URL="${REMOTE_WEB_URL%.git}"
if [[ "$REMOTE_WEB_URL" == http://* || "$REMOTE_WEB_URL" == https://* ]]; then
  COMMIT_URL="$REMOTE_WEB_URL/commit/$COMMIT"
  SOURCE_COMMIT="[\`$COMMIT\`]($COMMIT_URL)"
else
  COMMIT_URL=""
  SOURCE_COMMIT="\`$COMMIT\`"
fi

if [ "${TRIVER_REBUILD_FRONTEND:-0}" = "1" ]; then
  echo "rebuilding frontend bundle"
  VITE_TRIVER_VERSION="$VERSION" \
  TRIVER_ENV_FILE="${TRIVER_RELEASE_ENV_FILE:-$ROOT_DIR/.env.example}" \
  TRIVER_LOCAL_DIR="$OUT_DIR/.release-local" \
  "$ROOT_DIR/scripts/build-frontend.sh"

  echo "frontend/package/build has been refreshed."
  echo "Commit the updated build files, then rerun this script without TRIVER_REBUILD_FRONTEND=1." >&2
  exit 0
fi

if [ "${TRIVER_REFRESH_FRONTEND_NOTICES:-0}" = "1" ]; then
  echo "collecting frontend npm notices"
  "$ROOT_DIR/scripts/collect-frontend-notices.sh"
  echo "THIRD_PARTY_NOTICES/frontend-npm has been refreshed."
  echo "Commit the updated notices, then rerun this script without TRIVER_REFRESH_FRONTEND_NOTICES=1." >&2
  exit 0
fi

if [ -n "$(git status --porcelain)" ] && [ "${TRIVER_ALLOW_DIRTY_RELEASE:-0}" != "1" ]; then
  echo "refusing to build release artifacts from a dirty worktree" >&2
  echo "commit changes first, or set TRIVER_ALLOW_DIRTY_RELEASE=1 for a local dry run" >&2
  exit 1
fi

if [ ! -f frontend/package/build/index.html ]; then
  echo "frontend/package/build/index.html is missing." >&2
  echo "Run VITE_TRIVER_VERSION=\"$VERSION\" ./scripts/build-frontend.sh and commit frontend/package/build." >&2
  exit 1
fi

private_hits_file="$(mktemp)"
frontend_private_pattern="${TRIVER_FRONTEND_PRIVATE_PATTERN:-127\.0\.0\.1|localhost|192\.168\.|10\.44\.0\.|ssh://git@|triver-live-proxy|triver-backend:3000|VITE_TRIVER_(BACKEND_UPSTREAM|VPN_ENDPOINT|VPN_WEB_URL|PROXY_VPN_IP|PROXY_ALLOWED_PORTS)|Reverse proxy|VPN edge|Deployment controls|Server Settings}"
if grep -RInE "$frontend_private_pattern" frontend/package/build >"$private_hits_file"; then
  cat "$private_hits_file" >&2
  rm -f "$private_hits_file"
  echo "frontend/package/build contains private/local deployment values; rebuild with ./scripts/build-frontend.sh" >&2
  exit 1
fi
rm -f "$private_hits_file"

echo "creating source archive"
git archive --format=tar.gz --prefix="trueriver-$VERSION/" -o "$OUT_DIR/trueriver-source-$VERSION.tar.gz" HEAD
tar -tzf "$OUT_DIR/trueriver-source-$VERSION.tar.gz" "trueriver-$VERSION/frontend/package/build/index.html" >/dev/null

echo "creating install archive with prebuilt frontend"
INSTALL_TMP="$OUT_DIR/.install-tree"
rm -rf "$INSTALL_TMP"
mkdir -p "$INSTALL_TMP"
git archive --format=tar --prefix="trueriver-$VERSION/" HEAD | tar -xf - -C "$INSTALL_TMP"
mv "$INSTALL_TMP/trueriver-$VERSION/README.md" "$INSTALL_TMP/trueriver-$VERSION/README.project.md"
cp "$ROOT_DIR/deploy/release/README.install.md" "$INSTALL_TMP/trueriver-$VERSION/README.md"
tar -C "$INSTALL_TMP" -czf "$OUT_DIR/trueriver-install-$VERSION.tar.gz" "trueriver-$VERSION"
rm -rf "$INSTALL_TMP"

tar -tzf "$OUT_DIR/trueriver-install-$VERSION.tar.gz" "trueriver-$VERSION/frontend/package/build/index.html" >/dev/null
tar -tzf "$OUT_DIR/trueriver-install-$VERSION.tar.gz" "trueriver-$VERSION/README.project.md" >/dev/null

echo "creating Windows install zip"
TRIVER_RELEASE_DIR="$OUT_DIR" "$ROOT_DIR/scripts/build-windows-package.sh" "$VERSION"

echo "creating frontend and notice archives"
ROOT_DIR="$ROOT_DIR" OUT_DIR="$OUT_DIR" VERSION="$VERSION" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
out_dir = Path(os.environ["OUT_DIR"])
version = os.environ["VERSION"]


def write_zip(zip_path, sources):
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, prefix in sources:
            source = Path(source)
            if source.is_file():
                archive.write(source, prefix / source.name)
                continue
            for item in sorted(source.rglob("*")):
                if item.is_file():
                    archive.write(item, prefix / item.relative_to(source))


web_build = root / "frontend" / "package" / "build"
if not web_build.is_dir():
    raise SystemExit("frontend/package/build is missing")

write_zip(
    out_dir / f"trueriver-web-{version}.zip",
    [(web_build, Path(f"trueriver-web-{version}"))],
)

notice_sources = [
    (root / "NOTICE.md", Path(f"trueriver-third-party-notices-{version}")),
    (root / "LICENSE", Path(f"trueriver-third-party-notices-{version}")),
    (root / "COPYRIGHT", Path(f"trueriver-third-party-notices-{version}")),
    (root / "AUTHORS", Path(f"trueriver-third-party-notices-{version}")),
    (root / "THIRD_PARTY_NOTICES", Path(f"trueriver-third-party-notices-{version}") / "THIRD_PARTY_NOTICES"),
    (root / "docs" / "build" / "frontend.md", Path(f"trueriver-third-party-notices-{version}") / "docs" / "build"),
    (root / "docs" / "build" / "android-tv.md", Path(f"trueriver-third-party-notices-{version}") / "docs" / "build"),
]
write_zip(out_dir / f"trueriver-third-party-notices-{version}.zip", notice_sources)
PY

APK_SOURCE="${TRIVER_APK_PATH:-}"
if [ -n "$APK_SOURCE" ] && [ -f "$APK_SOURCE" ]; then
  cp "$APK_SOURCE" "$OUT_DIR/trueriver-tv-$VERSION.apk"
else
  cat > "$OUT_DIR/APK_NOT_INCLUDED.txt" <<EOF
No Android TV APK was included in this artifact set.

Set TRIVER_APK_PATH to a built release APK before running this script for a
public release. Debug APKs are not public release artifacts.
EOF
fi

cat > "$OUT_DIR/release-notes-$VERSION.md" <<EOF
# trueRiver $VERSION

Source commit: $SOURCE_COMMIT
Source tag: \`${TAG:-not tagged}\`
Source remote: \`${REMOTE_URL:-not configured}\`

## Artifacts

- \`trueriver-install-$VERSION.tar.gz\`: installable server archive with a short install README and the prebuilt web frontend included under \`frontend/package/build/\`.
- \`trueriver-windows-$VERSION.zip\`: Windows install archive with PowerShell helpers for Docker Desktop and the prebuilt web frontend.
- \`trueriver-source-$VERSION.tar.gz\`: complete source archive generated from the commit above, including the prebuilt web frontend under \`frontend/package/build/\`.
- \`trueriver-web-$VERSION.zip\`: built web frontend.
- \`trueriver-third-party-notices-$VERSION.zip\`: license texts and third-party notices.
- \`trueriver-tv-$VERSION.apk\`: Android TV APK, when supplied through \`TRIVER_APK_PATH\`.
- \`checksums.txt\`: SHA-256 checksums for release attachments.

Use \`trueriver-install-$VERSION.tar.gz\` for the shortest normal server install
path. A Git checkout or source archive from the same commit also includes the
prebuilt web frontend and can be deployed without Node/npm.

The release page must link these artifacts to the exact source tag or commit above.
EOF

(
  cd "$OUT_DIR"
  rm -f checksums.txt
  find . -maxdepth 1 -type f ! -name checksums.txt -printf '%f\n' | sort | xargs -r sha256sum > checksums.txt
)

echo "release artifacts written to $OUT_DIR"
