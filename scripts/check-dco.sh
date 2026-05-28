#!/usr/bin/env bash
set -euo pipefail

range="${1:-origin/main..HEAD}"

missing=0
while IFS= read -r commit; do
  [ -n "$commit" ] || continue
  if ! git log -1 --format=%B "$commit" | grep -qi '^Signed-off-by: .\+ <.\+@.\+>$'; then
    echo "Missing DCO sign-off: $commit"
    missing=1
  fi
done < <(git rev-list "$range")

if [ "$missing" -ne 0 ]; then
  echo
  echo "Add a sign-off with: git commit -s"
  echo "For the latest commit only: git commit --amend -s --no-edit"
  exit 1
fi

echo "DCO sign-off check passed for range: $range"
