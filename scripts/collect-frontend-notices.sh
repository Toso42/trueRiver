#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/source"
OUT_DIR="$ROOT_DIR/THIRD_PARTY_NOTICES/frontend-npm"

cd "$ROOT_DIR"

if [ ! -f "$FRONTEND_DIR/package-lock.json" ]; then
  echo "missing frontend/source/package-lock.json" >&2
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  if command -v npm >/dev/null 2>&1; then
    (cd "$FRONTEND_DIR" && npm ci --ignore-scripts)
  elif command -v docker >/dev/null 2>&1; then
    docker run --rm \
      -v "$FRONTEND_DIR:/frontend" \
      -w /frontend \
      node:20-alpine \
      sh -lc "npm ci --ignore-scripts"
  else
    echo "frontend/source/node_modules is missing and neither npm nor docker is available" >&2
    exit 1
  fi
fi

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/packages"

ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
import json
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
frontend = root / "frontend" / "source"
node_modules = frontend / "node_modules"
out_dir = root / "THIRD_PARTY_NOTICES" / "frontend-npm"
packages_dir = out_dir / "packages"
lock_path = frontend / "package-lock.json"

license_name = re.compile(r"^(licen[cs]e|notice|copying|copyright)(\..*)?$", re.IGNORECASE)

with lock_path.open("r", encoding="utf-8") as handle:
    lock = json.load(handle)

lock_packages = lock.get("packages", {})


def package_root_names():
    names = []
    for entry in sorted(node_modules.iterdir(), key=lambda path: path.name.lower()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if entry.name.startswith("@"):
            for child in sorted(entry.iterdir(), key=lambda path: path.name.lower()):
                if child.is_dir() and (child / "package.json").is_file():
                    names.append(f"{entry.name}/{child.name}")
        elif (entry / "package.json").is_file():
            names.append(entry.name)
    return names


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.replace("@", "at_").replace("/", "__"))


def package_dir(name):
    return node_modules.joinpath(*name.split("/"))


def lock_entry(name):
    return lock_packages.get(f"node_modules/{name}", {})


def copy_notice_files(src, dest):
    copied = []
    for item in sorted(src.iterdir(), key=lambda path: path.name.lower()):
        if item.is_file() and license_name.match(item.name):
            target = dest / item.name
            try:
                text = item.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copyfile(item, target)
            else:
                normalized = "\n".join(line.rstrip() for line in text.splitlines())
                if text.endswith(("\n", "\r\n")):
                    normalized += "\n"
                target.write_text(normalized, encoding="utf-8")
            copied.append(item.name)
    return copied


rows = []
for name in package_root_names():
    src = package_dir(name)
    with (src / "package.json").open("r", encoding="utf-8") as handle:
        package_json = json.load(handle)

    meta = lock_entry(name)
    version = package_json.get("version") or meta.get("version") or ""
    license_value = package_json.get("license") or meta.get("license") or ""
    resolved = meta.get("resolved") or package_json.get("homepage") or ""
    integrity = meta.get("integrity") or ""

    dest = packages_dir / safe_name(name)
    dest.mkdir(parents=True, exist_ok=True)
    copied_files = copy_notice_files(src, dest)

    metadata = {
        "name": name,
        "version": version,
        "license": license_value,
        "resolved": resolved,
        "integrity": integrity,
        "packageJsonLicense": package_json.get("license", ""),
        "lockfileLicense": meta.get("license", ""),
        "noticeFiles": copied_files,
    }
    with (dest / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")

    rows.append(metadata)

missing_files = [row for row in rows if not row["noticeFiles"]]

index_lines = [
    "# Frontend npm Package Notices",
    "",
    "Generated from `frontend/source/package-lock.json` and the installed `frontend/source/node_modules` tree.",
    "",
    "This directory is a conservative notice bundle for the web frontend release artifact. It may include build-time packages in addition to runtime browser code, which is acceptable for release packaging.",
    "",
    "Regenerate with:",
    "",
    "```bash",
    "./scripts/collect-frontend-notices.sh",
    "```",
    "",
    "The full common license texts are kept one directory up in `THIRD_PARTY_NOTICES/`.",
    "",
    "| Package | Version | License | Copied notice files | Source |",
    "| --- | ---: | --- | --- | --- |",
]

for row in sorted(rows, key=lambda item: item["name"].lower()):
    files = ", ".join(f"`{name}`" for name in row["noticeFiles"]) if row["noticeFiles"] else "_none found in installed package root_"
    source = row["resolved"] or ""
    index_lines.append(
        f"| `{row['name']}` | {row['version']} | {row['license']} | {files} | {source} |"
    )

index_lines.extend([
    "",
    "## Packages Without Root Notice Files",
    "",
])

if missing_files:
    for row in sorted(missing_files, key=lambda item: item["name"].lower()):
        index_lines.append(f"- `{row['name']}@{row['version']}` (`{row['license']}`)")
else:
    index_lines.append("All installed package roots had a copied notice file.")

index_lines.extend([
    "",
    "## Scope",
    "",
    "This bundle covers packages installed on the release build host. Optional platform packages listed in `package-lock.json` but not installed on this host are tracked in `docs/release-audit/current/frontend-npm-licenses.md` and are not shipped in the generated web frontend bundle.",
])

(out_dir / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

print(f"wrote {len(rows)} package notice entries to {out_dir.relative_to(root)}")
PY
