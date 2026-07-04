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

# --- Deployed dev box (behind the nina-dev nginx that terminates TLS) ---
# Harmless on a laptop: nothing sets X-Forwarded-Proto there, so scheme stays http.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Trust the dev apex + tenant subdomains for admin CSRF over HTTPS.
_base = env("BASE_DOMAIN", default="localhost")
CSRF_TRUSTED_ORIGINS = [
    f"https://{_base}",
    f"https://*.{_base}",
    f"http://{_base}",
    f"http://*.{_base}",
]
