"""Local development settings."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]  # dev only; wildcard subdomains resolve to any *.localhost

# Console email backend in dev.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Run Celery tasks synchronously unless a worker is explicitly desired.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)

INTERNAL_IPS = ["127.0.0.1"]
