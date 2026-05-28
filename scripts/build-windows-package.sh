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
  exit 1
fi
if triver_version_is_semver "$VERSION"; then
  VERSION="$(triver_version_with_v "$VERSION")"
fi

OUT_DIR="${TRIVER_RELEASE_DIR:-$ROOT_DIR/release/artifacts/$VERSION}"
mkdir -p "$OUT_DIR"

if [ ! -f frontend/package/build/index.html ]; then
  echo "frontend/package/build/index.html is missing." >&2
  echo "Windows packages include the prebuilt web frontend; build and commit it first." >&2
  exit 1
fi

TMP_DIR="$OUT_DIR/.windows-tree"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

git archive --format=tar --prefix="trueriver-$VERSION/" HEAD | tar -xf - -C "$TMP_DIR"
mv "$TMP_DIR/trueriver-$VERSION/README.md" "$TMP_DIR/trueriver-$VERSION/README.project.md"
cp "$ROOT_DIR/deploy/windows/README.windows.md" "$TMP_DIR/trueriver-$VERSION/README.md"

ROOT_DIR="$ROOT_DIR" OUT_DIR="$OUT_DIR" VERSION="$VERSION" TMP_DIR="$TMP_DIR" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

out_dir = Path(os.environ["OUT_DIR"])
version = os.environ["VERSION"]
tree_root = Path(os.environ["TMP_DIR"]) / f"trueriver-{version}"
zip_path = out_dir / f"trueriver-windows-{version}.zip"

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for item in sorted(tree_root.rglob("*")):
        if item.is_file():
            archive.write(item, tree_root.name / item.relative_to(tree_root))
PY

rm -rf "$TMP_DIR"
echo "Windows package written to $OUT_DIR/trueriver-windows-$VERSION.zip"
