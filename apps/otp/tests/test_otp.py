"""OTP engine: request -> verify, rate-limit, expiry, attempt cap, token scoping."""

import pytest
from django.utils import timezone

from apps.common.exceptions import DomainError
from apps.otp import services
from apps.otp.models import OtpCode

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fixed_code(monkeypatch):
    """Deterministic code so tests can 'read' it (console provider sends nothing)."""
    monkeypatch.setattr(services, "_generate_code", lambda: "123456")


def test_request_then_verify_returns_valid_token():
    services.request_otp("0912 345 6789", "booking")
    token = services.verify_otp("09123456789", "booking", "123456")
    assert services.check_verification_token(token, "09123456789", "booking")
    # token is scoped to (phone, purpose)
    assert not services.check_verification_token(token, "09120000000", "booking")
    assert not services.check_verification_token(token, "09123456789", "signup")


def test_phone_is_normalised_across_formats():
    services.request_otp("+989123456789", "signup")
    # verify with a different surface format for the same number
    token = services.verify_otp("0912-345-6789", "signup", "123456")
    assert services.check_verification_token(token, "989123456789", "signup")


def test_wrong_code_increments_attempts_and_locks():
    services.request_otp("09120000001", "booking")
    for _ in range(5):
        with pytest.raises(DomainError) as exc:
            services.verify_otp("09120000001", "booking", "000000")
        assert exc.value.code == "otp_invalid"
    # 6th attempt: locked
    with pytest.raises(DomainError) as exc:
        services.verify_otp("09120000001", "booking", "123456")
    assert exc.value.code == "otp_locked"


def test_cooldown_blocks_rapid_resend():
    services.request_otp("09120000002", "booking")
    with pytest.raises(DomainError) as exc:
        services.request_otp("09120000002", "booking")
    assert exc.value.code == "otp_cooldown"


def test_expired_code_rejected():
    services.request_otp("09120000003", "signup")
    otp = OtpCode.objects.filter(identifier="09120000003").first()
    otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    otp.save(update_fields=["expires_at"])
    with pytest.raises(DomainError) as exc:
        services.verify_otp("09120000003", "signup", "123456")
    assert exc.value.code == "otp_expired"


def test_consumed_code_cannot_be_reused():
    services.request_otp("09120000004", "booking")
    services.verify_otp("09120000004", "booking", "123456")
    with pytest.raises(DomainError) as exc:
        services.verify_otp("09120000004", "booking", "123456")
    assert exc.value.code == "otp_not_found"
