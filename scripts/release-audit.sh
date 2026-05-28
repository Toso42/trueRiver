#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${1:-docs/release-audit/current}"
mkdir -p "$OUT_DIR"

run_if_available() {
  local tool="$1"
  shift
  if command -v "$tool" >/dev/null 2>&1; then
    echo "running: $tool $*"
    "$tool" "$@"
  else
    echo "missing: $tool"
    return 127
  fi
}

{
  echo "# Scanner Availability"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "| Tool | Status |"
  echo "| --- | --- |"
  for tool in reuse scancode jscpd gitleaks trufflehog npm python3 gradle; do
    if command -v "$tool" >/dev/null 2>&1; then
      echo "| \`$tool\` | available: \`$(command -v "$tool")\` |"
    else
      echo "| \`$tool\` | missing |"
    fi
  done
} > "$OUT_DIR/scanner-availability.md"

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --source . --redact --report-format json --report-path "$OUT_DIR/gitleaks.json"
else
  echo "gitleaks not installed; skipped."
fi

if command -v trufflehog >/dev/null 2>&1; then
  trufflehog filesystem --json . > "$OUT_DIR/trufflehog.json"
else
  echo "trufflehog not installed; skipped."
fi

if command -v reuse >/dev/null 2>&1; then
  reuse lint > "$OUT_DIR/reuse-lint.txt"
else
  echo "reuse not installed; skipped."
fi

if command -v jscpd >/dev/null 2>&1; then
  jscpd --reporters markdown --output "$OUT_DIR/jscpd" .
else
  echo "jscpd not installed; skipped."
fi

if command -v scancode >/dev/null 2>&1; then
  scancode --license --copyright --summary --json-pp "$OUT_DIR/scancode.json" .
else
  echo "scancode not installed; skipped."
fi

echo "Release audit metadata written to $OUT_DIR"
