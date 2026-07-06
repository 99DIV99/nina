"""Structured logging configuration (JSON in prod, readable in dev)."""

import os

_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.common.logging.JSONFormatter",
        },
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if os.environ.get("DJANGO_LOG_JSON") else "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": _LEVEL,
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "nina": {"handlers": ["console"], "level": _LEVEL, "propagate": False},
    },
}
