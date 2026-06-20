"""Staging settings: production-like, with looser diagnostics."""

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, STORAGES, env

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[".yourapp.com"])

# Serve hashed static files from gunicorn (nginx proxies /static here).
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 3600

# Secure cookies by default; set DJANGO_SECURE_COOKIES=false for the HTTP-first
# bring-up so the admin session/CSRF cookies are sent over plain HTTP.
_secure_cookies = env.bool("DJANGO_SECURE_COOKIES", default=True)
SESSION_COOKIE_SECURE = _secure_cookies
CSRF_COOKIE_SECURE = _secure_cookies

# Trust the apex + every tenant subdomain for admin form POSTs (CSRF origin check).
_base = env("BASE_DOMAIN", default="yourapp.com")
CSRF_TRUSTED_ORIGINS = [
    f"http://{_base}",
    f"https://{_base}",
    f"http://*.{_base}",
    f"https://*.{_base}",
]

_sentry_dsn = env("SENTRY_DSN", default="")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=False,
        environment="staging",
    )
