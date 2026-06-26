"""Subdomain validation + reserved-name protection (B1)."""

import re

from django.conf import settings

from apps.common.exceptions import DomainError

MAX_SUBDOMAIN_LEN = 16
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,14}[a-z0-9])?$")


def normalize_subdomain(raw: str) -> str:
    return (raw or "").strip().lower()


def validate_subdomain(raw: str) -> str:
    """Return a normalized subdomain or raise DomainError."""
    sub = normalize_subdomain(raw)
    if not sub:
        raise DomainError("Subdomain is required.", code="subdomain_required")
    if len(sub) > MAX_SUBDOMAIN_LEN:
        raise DomainError(
            f"Subdomain must be at most {MAX_SUBDOMAIN_LEN} characters.",
            code="subdomain_too_long",
        )
    if not _SUBDOMAIN_RE.match(sub):
        raise DomainError(
            f"Subdomain must be 2-{MAX_SUBDOMAIN_LEN} chars, lowercase letters, digits "
            "or hyphens, not starting/ending with a hyphen.",
            code="subdomain_invalid",
        )
    if "--" in sub:
        raise DomainError(
            "Subdomain may not contain consecutive hyphens.", code="subdomain_invalid"
        )
    if sub in settings.RESERVED_SUBDOMAINS:
        raise DomainError("That subdomain is reserved.", code="subdomain_reserved")
    return sub


def is_available(raw: str) -> bool:
    """True if the subdomain is valid AND not already taken."""
    from apps.tenancy.models import Domain

    try:
        sub = validate_subdomain(raw)
    except DomainError:
        return False
    host = f"{sub}.{settings.BASE_DOMAIN}"
    return not Domain.objects.filter(domain=host).exists()
