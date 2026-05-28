from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        return max(minimum, value)
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        return max(minimum, value)
    return value


DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "triver-dev-secret-change-me"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is disabled.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "apps.core",
    "apps.library",
    "apps.catalog",
    "apps.tags",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "triver.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "triver.wsgi.application"
ASGI_APPLICATION = "triver.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "triver"),
        "USER": os.environ.get("POSTGRES_USER", "triver"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "triver"),
        "HOST": os.environ.get("POSTGRES_HOST", "triver-db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "utils.pagination.TriverPageNumberPagination",
    "PAGE_SIZE": 40,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://triver-valkey:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://triver-valkey:6379/2")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = _env_int("TRIVER_CELERY_WORKER_PREFETCH_MULTIPLIER", 1, minimum=1)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_VISIBILITY_TIMEOUT = _env_int("CELERY_VISIBILITY_TIMEOUT", 21600, minimum=60)
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": CELERY_VISIBILITY_TIMEOUT}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"visibility_timeout": CELERY_VISIBILITY_TIMEOUT}
TRIVER_DIGEST_BATCH_SIZE = _env_int("TRIVER_DIGEST_BATCH_SIZE", 1, minimum=1)
TRIVER_DIGEST_PROGRESS_INTERVAL = _env_int("TRIVER_DIGEST_PROGRESS_INTERVAL", 1, minimum=1)
TRIVER_DIGEST_PARALLEL_BATCHES = _env_bool("TRIVER_DIGEST_PARALLEL_BATCHES", False)
TRIVER_DIGEST_ITEM_SLEEP_SECONDS = _env_float("TRIVER_DIGEST_ITEM_SLEEP_SECONDS", 0.35, minimum=0.0)
TRIVER_DIGEST_BATCH_SLEEP_SECONDS = _env_float("TRIVER_DIGEST_BATCH_SLEEP_SECONDS", 0.0, minimum=0.0)
TRIVER_DIGEST_FULL_CONTENT_HASH = _env_bool("TRIVER_DIGEST_FULL_CONTENT_HASH", False)
TRIVER_DIGEST_CONTENT_HASH_MAX_BYTES = _env_int("TRIVER_DIGEST_CONTENT_HASH_MAX_BYTES", 0, minimum=0)
TRIVER_DIGEST_HASH_CHUNK_BYTES = _env_int("TRIVER_DIGEST_HASH_CHUNK_BYTES", 256 * 1024, minimum=64 * 1024)
TRIVER_DIGEST_HASH_BYTES_PER_SECOND = _env_int("TRIVER_DIGEST_HASH_BYTES_PER_SECOND", 1024 * 1024, minimum=0)
TRIVER_SCAN_SLEEP_EVERY = _env_int("TRIVER_SCAN_SLEEP_EVERY", 20, minimum=1)
TRIVER_SCAN_ITEM_SLEEP_SECONDS = _env_float("TRIVER_SCAN_ITEM_SLEEP_SECONDS", 0.02, minimum=0.0)
TRIVER_AUTO_IMPORT_POLL_SECONDS = _env_int("TRIVER_AUTO_IMPORT_POLL_SECONDS", 120, minimum=15)
TRIVER_AUTO_IMPORT_QUIET_SECONDS = _env_int("TRIVER_AUTO_IMPORT_QUIET_SECONDS", 90, minimum=0)
TRIVER_AUTO_IMPORT_SCAN_SLEEP_EVERY = _env_int("TRIVER_AUTO_IMPORT_SCAN_SLEEP_EVERY", 250, minimum=1)
TRIVER_AUTO_IMPORT_SCAN_SLEEP_SECONDS = _env_float("TRIVER_AUTO_IMPORT_SCAN_SLEEP_SECONDS", 0.01, minimum=0.0)
TRIVER_DEDUP_SCAN_SLEEP_EVERY = _env_int("TRIVER_DEDUP_SCAN_SLEEP_EVERY", 25, minimum=1)
TRIVER_DEDUP_SCAN_SLEEP_SECONDS = _env_float("TRIVER_DEDUP_SCAN_SLEEP_SECONDS", 0.05, minimum=0.0)
TRIVER_DEDUP_MAX_CANDIDATES = _env_int("TRIVER_DEDUP_MAX_CANDIDATES", 200, minimum=1)

CELERY_BEAT_SCHEDULE = {
    "triver-auto-import-monitor": {
        "task": "apps.library.tasks.run_auto_import_monitor",
        "schedule": float(TRIVER_AUTO_IMPORT_POLL_SECONDS),
        "options": {"expires": max(TRIVER_AUTO_IMPORT_POLL_SECONDS * 2, 60)},
    },
}

TRIVER_INGEST_ROOT = os.environ.get("TRIVER_INGEST_ROOT", "/srv/triver/trive-In")
TRIVER_DIGEST_ROOT = os.environ.get("TRIVER_DIGEST_ROOT", "/srv/triver/trive-Up")
TRIVER_NORMALIZE_ROOT = os.environ.get("TRIVER_NORMALIZE_ROOT", "/srv/triver/trive-Out")
TRIVER_DUMP_ROOT = os.environ.get("TRIVER_DUMP_ROOT", "/srv/triver/trive-dump")
TRIVER_CLASSIC_IMPORT_SOURCES = os.environ.get("TRIVER_CLASSIC_IMPORT_SOURCES", "")
TRIVER_USER_AVATAR_ROOT = os.environ.get("TRIVER_USER_AVATAR_ROOT", str(Path(TRIVER_DUMP_ROOT) / "user-avatars"))
TRIVER_CLAMAV_ENABLED = os.environ.get("TRIVER_CLAMAV_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
TRIVER_CLAMAV_HOST = os.environ.get("TRIVER_CLAMAV_HOST", "triver-clamav")
TRIVER_CLAMAV_PORT = int(os.environ.get("TRIVER_CLAMAV_PORT", "3310"))
TRIVER_UPLOAD_SCAN_CHUNK_BYTES = int(os.environ.get("TRIVER_UPLOAD_SCAN_CHUNK_BYTES", str(1024 * 1024)))
