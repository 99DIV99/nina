"""OTP engine: request -> verify, rate-limit, expiry, attempt cap, token scoping."""

import json
import urllib.request

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.common.exceptions import DomainError
from apps.otp import services
from apps.otp.models import OtpCode
from apps.otp.providers import IranPayamakProvider

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


# --- IranPayamak per-purpose pattern split ---------------------------------


@override_settings(
    IRANPAYAMAK_PATTERN_BOOKING="bookpat",
    IRANPAYAMAK_PATTERN_SIGNUP="signpat",
    IRANPAYAMAK_PATTERN_CODE="generic",
)
def test_pattern_selected_per_purpose():
    p = IranPayamakProvider()
    assert p._pattern_for("booking") == "bookpat"
    assert p._pattern_for("signup") == "signpat"
    assert p._pattern_for("other") == "generic"  # unknown purpose -> generic fallback


@override_settings(IRANPAYAMAK_PATTERN_BOOKING="", IRANPAYAMAK_PATTERN_CODE="generic")
def test_pattern_falls_back_when_per_purpose_unset():
    assert IranPayamakProvider()._pattern_for("booking") == "generic"


class _FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"status": "success"}'


def _capture_send(monkeypatch) -> dict:
    """Intercept the outgoing HTTP request and capture its JSON body."""
    captured: dict = {}

    def fake_urlopen(req, timeout=10):
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


@override_settings(
    IRANPAYAMAK_API_KEY="k",
    IRANPAYAMAK_LINE_NUMBER="3000505",
    IRANPAYAMAK_PATTERN_BOOKING="bookpat",
    IRANPAYAMAK_BUSINESS_MAX_LEN=5,
)
def test_booking_sends_truncated_business_name(monkeypatch):
    captured = _capture_send(monkeypatch)
    ok = IranPayamakProvider().send_otp(
        "09120000000", "123456", purpose="booking", business="VeryLongSalonName"
    )
    assert ok
    body = captured["body"]
    assert body["code"] == "bookpat"
    variables = body["attributes"]
    assert variables["code"] == "123456"
    assert variables["business_name"] == "VeryL"  # truncated to 5 chars


@override_settings(
    IRANPAYAMAK_API_KEY="k",
    IRANPAYAMAK_LINE_NUMBER="3000505",
    IRANPAYAMAK_PATTERN_SIGNUP="signpat",
)
def test_signup_sends_code_only(monkeypatch):
    captured = _capture_send(monkeypatch)
    ok = IranPayamakProvider().send_otp("09120000000", "123456", purpose="signup")
    assert ok
    body = captured["body"]
    assert body["code"] == "signpat"
    assert body["attributes"] == {"code": "123456"}  # no business_name variable
