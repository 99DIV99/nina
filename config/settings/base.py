"""
Base settings shared across all environments.

Architectural notes (see booking-saas-build-tasklist.md):
- Multi-tenant, schema-per-tenant via django-tenants. The schema IS the isolation
  boundary; tenant apps carry no business_id.
- SHARED_APPS live in the public schema; TENANT_APPS are cloned per tenant schema.
- TenantMainMiddleware must be first in the stack so the schema is switched before
  anything else runs.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)

# Read .env if present (local/dev). In prod, real env vars take precedence.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    env.read_env(str(_env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# The apex domain used to derive subdomains, e.g. acme.yourapp.com -> "acme".
BASE_DOMAIN = env("BASE_DOMAIN", default="localhost")

# Hosts that serve the unified business dashboard (the panel for every business).
# On these hosts there is no tenant in the hostname, so the active business is
# resolved from the authenticated JWT's `biz` claim — see
# apps.tenancy.middleware.TenantMainMiddleware. Booking subdomains + the apex keep
# host-based resolution.
NINA_DASHBOARD_HOSTS = env.list("NINA_DASHBOARD_HOSTS", default=["dash.localhost"])

# ---------------------------------------------------------------------------
# Applications: SHARED (public schema) vs TENANT (per-schema)
# ---------------------------------------------------------------------------
SHARED_APPS = [
    "django_tenants",  # must come first
    "apps.tenancy",  # Business (tenant) + Domain models live in public schema
    "apps.accounts",  # users belong to tenants from the public schema
    # Django contrib needed in public schema
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",  # operator/system-admin console (public schema)
    "django.contrib.sessions",  # required by admin (session auth)
    "django.contrib.messages",  # required by admin
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # ExclusionConstraint / range types (booking)
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # audit/revoke issued refresh tokens
    "drf_spectacular",
    "corsheaders",
    "django_celery_beat",
    "apps.otp",  # SMS OTP — public schema serves owner-signup verification
]

TENANT_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    # Per-tenant business modules
    "apps.business",  # business config, feature flags, branding, vocabulary
    "apps.booking",  # services, staff, customers, appointments, availability
    "apps.notifications",  # reminders / confirmations
    "apps.accounting",  # flag-gated bookkeeping
    "apps.bots",  # per-tenant booking bots
    "apps.audit",  # audit log (per tenant)
    "apps.otp",  # SMS OTP — tenant schema serves customer-booking verification
]

# INSTALLED_APPS = union, preserving order, no duplicates.
INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

TENANT_MODEL = "tenancy.Business"
TENANT_DOMAIN_MODEL = "tenancy.Domain"

# Custom user model lives in the public (shared) schema.
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Middleware: TenantMainMiddleware FIRST.
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "apps.tenancy.middleware.TenantMainMiddleware",  # host- OR token-based tenant resolution
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"

WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database: django-tenants backend (PostgreSQL only).
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": env("POSTGRES_DB", default="nina"),
        "USER": env("POSTGRES_USER", default="nina"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="nina"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}

DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# i18n / tz: store/compute in UTC; per-tenant/staff tz handled in booking layer.
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django_tenants.staticfiles.storage.TenantStaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# DRF + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "240/min",
        "auth": "10/min",
        "bot": "120/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "NINA Booking & Bookkeeping API",
    "DESCRIPTION": "Multi-tenant booking SaaS. Schema-per-tenant; server-side authz is absolute.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Tenancy guardrails
# ---------------------------------------------------------------------------
# Subdomains that may never be claimed by a tenant.
RESERVED_SUBDOMAINS = {
    "www",
    "api",
    "admin",
    "app",
    "mail",
    "ftp",
    "smtp",
    "imap",
    "pop",
    "ns",
    "ns1",
    "ns2",
    "dns",
    "static",
    "assets",
    "cdn",
    "media",
    "img",
    "blog",
    "help",
    "support",
    "docs",
    "status",
    "billing",
    "dashboard",
    "console",
    "internal",
    "staging",
    "dev",
    "test",
    "demo",
    "public",
    "operator",
    "system",
    "root",
    "security",
    "auth",
    "login",
    "signup",
}

# Email
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@yourapp.com")
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# SMS / OTP. Default "console" logs the code (works with no credentials); set
# SMS_PROVIDER=iranpayamak + the API key/line to deliver real SMS.
SMS_PROVIDER = env("SMS_PROVIDER", default="console")
IRANPAYAMAK_API_KEY = env("IRANPAYAMAK_API_KEY", default="")
IRANPAYAMAK_LINE_NUMBER = env("IRANPAYAMAK_LINE_NUMBER", default="")  # a service (خدماتی) line
# One pattern per purpose — the wording differs, so each is its own approved
# template. Booking uses %business_name% + %code%; signup uses %code% only.
# Falls back to the generic IRANPAYAMAK_PATTERN_CODE when a per-purpose one is unset.
IRANPAYAMAK_PATTERN_CODE = env("IRANPAYAMAK_PATTERN_CODE", default="")
IRANPAYAMAK_PATTERN_BOOKING = env("IRANPAYAMAK_PATTERN_BOOKING", default="")
IRANPAYAMAK_PATTERN_SIGNUP = env("IRANPAYAMAK_PATTERN_SIGNUP", default="")
# Pattern variable names — must match the %placeholders% you defined in the panel.
IRANPAYAMAK_VAR_CODE = env("IRANPAYAMAK_VAR_CODE", default="code")
IRANPAYAMAK_VAR_BUSINESS = env("IRANPAYAMAK_VAR_BUSINESS", default="business_name")
# Business name is truncated to this many chars so a long name can't break delivery
# (must not exceed the pattern variable's length limit registered in the panel).
IRANPAYAMAK_BUSINESS_MAX_LEN = env.int("IRANPAYAMAK_BUSINESS_MAX_LEN", default=40)
OTP_SMS_TEMPLATE = env("OTP_SMS_TEMPLATE", default="Your verification code: {code}")

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https?://([a-z0-9-]+\.)?localhost(:\d+)?$"]

# Channel for cross-cutting structured logging config (see logging.py import below).
from .logging import LOGGING  # noqa: E402,F401
