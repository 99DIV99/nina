"""Auth-related services: lockout, verification tokens, password reset."""

from datetime import timedelta

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

_email_signer = TimestampSigner(salt="nina.email.verify")
_reset_signer = TimestampSigner(salt="nina.password.reset")


def register_failed_login(user) -> None:
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = timezone.now() + LOCKOUT_DURATION
    user.save(update_fields=["failed_login_attempts", "locked_until"])


def register_successful_login(user) -> None:
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until"])


def tokens_for_user(user) -> dict:
    """Mint access+refresh JWTs for `user`. The refresh token is recorded in the
    public schema (token_blacklist OutstandingToken) regardless of the active
    schema, so issued tokens are always auditable/revocable from one place."""
    from django_tenants.utils import get_public_schema_name, schema_context
    from rest_framework_simplejwt.tokens import RefreshToken

    with schema_context(get_public_schema_name()):
        refresh = RefreshToken.for_user(user)
        return {"access": str(refresh.access_token), "refresh": str(refresh)}


def make_email_verification_token(user) -> str:
    return _email_signer.sign(str(user.pk))


def verify_email_token(token: str, max_age_hours: int = 48):
    try:
        pk = _email_signer.unsign(token, max_age=max_age_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return pk


def make_password_reset_token(user) -> str:
    return _reset_signer.sign(str(user.pk))


def verify_password_reset_token(token: str, max_age_hours: int = 2):
    try:
        pk = _reset_signer.unsign(token, max_age=max_age_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return pk
