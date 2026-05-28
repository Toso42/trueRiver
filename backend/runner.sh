#!/usr/bin/env bash
set -euo pipefail

cd /backend

exec_with_worker_priority() {
  local command=("$@")
  local nice_level="${TRIVER_WORKER_NICE:-10}"
  local ionice_class="${TRIVER_WORKER_IONICE_CLASS:-2}"
  local ionice_level="${TRIVER_WORKER_IONICE_LEVEL:-7}"

  if command -v nice >/dev/null 2>&1 && [[ -n "$nice_level" ]]; then
    command=(nice -n "$nice_level" "${command[@]}")
  fi
  if command -v ionice >/dev/null 2>&1 && [[ -n "$ionice_class" ]]; then
    command=(ionice -c "$ionice_class" -n "$ionice_level" "${command[@]}")
  fi

  exec "${command[@]}"
}

mode="${1:-web}"
case "$mode" in
  web)
    python manage.py migrate --noinput --fake-initial
    exec gunicorn triver.wsgi:application \
      --bind 0.0.0.0:3000 \
      --workers "${TRIVER_GUNICORN_WORKERS:-3}" \
      --timeout "${TRIVER_GUNICORN_TIMEOUT:-0}"
    ;;
  worker)
    until python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('db-ok')"; do
      sleep 2
    done
    exec_with_worker_priority celery -A triver worker -l info \
      --concurrency="${TRIVER_CELERY_WORKER_CONCURRENCY:-1}" \
      --prefetch-multiplier="${TRIVER_CELERY_WORKER_PREFETCH_MULTIPLIER:-1}" \
      --queues="${TRIVER_CELERY_WORKER_QUEUES:-celery}"
    ;;
  beat)
    until python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('db-ok')"; do
      sleep 2
    done
    exec celery -A triver beat -l info
    ;;
  *)
    echo "Unknown mode: $mode" >&2
    exit 1
    ;;
esac
