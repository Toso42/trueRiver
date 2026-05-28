from pathlib import Path
import os
import tempfile

from .settings import *  # noqa: F401,F403


TEST_ROOT = Path(os.environ.get("TRIVER_TEST_ROOT", tempfile.gettempdir())) / "triver-tests"
TEST_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

TRIVER_INGEST_ROOT = str(TEST_ROOT / "trive-In")
TRIVER_DIGEST_ROOT = str(TEST_ROOT / "trive-Up")
TRIVER_NORMALIZE_ROOT = str(TEST_ROOT / "trive-Out")
TRIVER_DUMP_ROOT = str(TEST_ROOT / "trive-dump")
TRIVER_USER_AVATAR_ROOT = str(TEST_ROOT / "user-avatars")
TRIVER_CLAMAV_ENABLED = False
