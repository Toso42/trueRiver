#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$#" -gt 0 ]; then
  test_targets=("$@")
else
  read -r -a test_targets <<< "${TRIVER_API_TEST_TARGETS:-apps.api apps.catalog apps.library}"
fi

"$ROOT_DIR/scripts/compose-local.sh" run --rm --no-deps triver-backend env \
  DJANGO_SETTINGS_MODULE="${TRIVER_TEST_SETTINGS_MODULE:-triver.test_settings}" \
  DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-triver-test-secret}" \
  DJANGO_DEBUG="${DJANGO_DEBUG:-1}" \
  python manage.py test "${test_targets[@]}"
