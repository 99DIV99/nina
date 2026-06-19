"""Test settings: fast, deterministic, Celery eager."""
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # faster tests

CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Speed: smaller throttles disabled in tests unless explicitly testing them.
REST_FRAMEWORK = dict(REST_FRAMEWORK)  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
