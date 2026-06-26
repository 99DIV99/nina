"""OTP generation, delivery, and verification."""

from __future__ import annotations

import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

from apps.common.exceptions import DomainError
from apps.otp.models import OtpCode
from apps.otp.providers import get_provider

_verified_signer = TimestampSigner(salt="nina.otp.verified")

# Tunables (overridable in settings).
TTL_SECONDS = getattr(settings, "OTP_TTL_SECONDS", 300)
COOLDOWN_SECONDS = getattr(settings, "OTP_COOLDOWN_SECONDS", 60)
MAX_PER_HOUR = getattr(settings, "OTP_MAX_PER_HOUR", 5)
CODE_LENGTH = getattr(settings, "OTP_CODE_LENGTH", 6)
VERIFIED_MAX_AGE = getattr(settings, "OTP_VERIFIED_MAX_AGE", 900)


def normalize_phone(raw: str) -> str:
    """Best-effort canonicalisation, tuned for Iranian mobiles (-> 09xxxxxxxxx)."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("+98"):
        digits = "0" + digits[3:]
    elif digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    return digits


def _generate_code() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(CODE_LENGTH))


def request_otp(raw_phone: str, purpose: str, *, business: str = "", action: str = "") -> dict:
    """Create + send an OTP, enforcing cooldown and hourly cap. `business`/`action`
    enrich the SMS pattern (who is asking / why). Raises DomainError."""
    phone = normalize_phone(raw_phone)
    if len(phone) < 7:
        raise DomainError("Enter a valid phone number.", code="invalid_phone")

    now = timezone.now()
    recent = OtpCode.objects.filter(
        identifier=phone, purpose=purpose, created_at__gte=now - timedelta(hours=1)
    )
    if recent.filter(created_at__gte=now - timedelta(seconds=COOLDOWN_SECONDS)).exists():
        raise DomainError(
            "Please wait before requesting another code.", code="otp_cooldown", status_code=429
        )
    if recent.count() >= MAX_PER_HOUR:
        raise DomainError(
            "Too many codes requested. Try again later.", code="otp_rate_limited", status_code=429
        )

    code = _generate_code()
    otp = OtpCode(
        identifier=phone, purpose=purpose, expires_at=now + timedelta(seconds=TTL_SECONDS)
    )
    otp.set_code(code)
    otp.save()

    if not get_provider().send_otp(phone, code, business=business, action=action):
        raise DomainError(
            "Could not send the code. Try again.", code="otp_send_failed", status_code=502
        )

    return {"phone": phone, "expires_in": TTL_SECONDS}


def verify_otp(raw_phone: str, purpose: str, code: str) -> str:
    """Verify a code; on success return a signed verification token. Raises DomainError."""
    phone = normalize_phone(raw_phone)
    otp = (
        OtpCode.objects.filter(identifier=phone, purpose=purpose, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        raise DomainError("Request a code first.", code="otp_not_found", status_code=404)
    if otp.is_expired:
        raise DomainError("That code has expired.", code="otp_expired")
    if otp.is_locked:
        raise DomainError(
            "Too many attempts. Request a new code.", code="otp_locked", status_code=429
        )

    if not otp.check_code((code or "").strip()):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise DomainError("Incorrect code.", code="otp_invalid")

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at"])
    return make_verification_token(phone, purpose)


def make_verification_token(phone: str, purpose: str) -> str:
    return _verified_signer.sign(f"{purpose}:{normalize_phone(phone)}")


def check_verification_token(token: str, raw_phone: str, purpose: str) -> bool:
    """True if `token` proves `phone` was OTP-verified for `purpose` recently."""
    try:
        value = _verified_signer.unsign(token, max_age=VERIFIED_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return value == f"{purpose}:{normalize_phone(raw_phone)}"
