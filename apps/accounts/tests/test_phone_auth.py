"""Phone-first auth: passwordless OTP login (primary) + sign-up convergence.

The console OTP provider is active in tests, so we freeze the generated code and
read it back. Endpoints live under /api/v1/auth/ and /api/v1/onboarding/, served
from the public schema (the dashboard/apex host).
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.otp import services
from conftest import make_user

pytestmark = pytest.mark.django_db(transaction=True)

DASH = "dash.localhost"


@pytest.fixture(autouse=True)
def fixed_code(monkeypatch):
    """Freeze the OTP code, and reset the throttle cache so the auth-scope rate
    limit (10/min) doesn't bleed across tests."""
    from django.core.cache import cache

    monkeypatch.setattr(services, "_generate_code", lambda: "123456")
    cache.clear()


def _client() -> APIClient:
    c = APIClient()
    c.credentials(HTTP_HOST=DASH)
    return c


# --- OTP login (primary, passwordless) -------------------------------------


def test_otp_login_request_unknown_phone_routes_to_signup():
    resp = _client().post("/api/v1/auth/otp/request", {"phone": "09120000099"}, format="json")
    assert resp.status_code == 200
    assert resp.json() == {"sent": False, "needs_signup": True}


def test_otp_login_request_existing_phone_sends_code():
    make_user(email="owner@x.io", phone="09120000001")
    resp = _client().post("/api/v1/auth/otp/request", {"phone": "09120000001"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


def test_otp_login_verify_returns_tokens():
    make_user(email="owner@x.io", phone="09120000001")
    c = _client()
    c.post("/api/v1/auth/otp/request", {"phone": "09120000001"}, format="json")
    resp = c.post(
        "/api/v1/auth/otp/verify", {"phone": "09120000001", "code": "123456"}, format="json"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access" in body and "refresh" in body


def test_otp_login_verify_wrong_code_rejected():
    make_user(email="owner@x.io", phone="09120000001")
    c = _client()
    c.post("/api/v1/auth/otp/request", {"phone": "09120000001"}, format="json")
    resp = c.post(
        "/api/v1/auth/otp/verify", {"phone": "09120000001", "code": "000000"}, format="json"
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "otp_invalid"


def test_otp_login_normalizes_phone_format():
    """Request in one format, verify in another — both canonicalise to one number."""
    make_user(email="owner@x.io", phone="09120000001")
    c = _client()
    c.post("/api/v1/auth/otp/request", {"phone": "+989120000001"}, format="json")
    resp = c.post(
        "/api/v1/auth/otp/verify", {"phone": "0912-000-0001", "code": "123456"}, format="json"
    )
    assert resp.status_code == 200
    assert "access" in resp.json()


# --- phone uniqueness (one phone == one business) --------------------------


def test_phone_is_unique_across_accounts():
    from django.db import IntegrityError

    make_user(email="a@x.io", phone="09120000002")
    with pytest.raises(IntegrityError):
        make_user(email="b@x.io", phone="09120000002")


def test_blank_phones_do_not_collide():
    make_user(email="a@x.io")
    make_user(email="b@x.io")
    assert User.objects.filter(phone="").count() >= 2


# --- sign-up convergence ---------------------------------------------------


def _signup_otp_token(phone: str) -> str:
    services.request_otp(phone, "signup")
    return services.verify_otp(phone, "signup", "123456")


def test_signup_with_registered_phone_logs_in():
    """A returning owner who hits sign-up with a known phone is logged in, not errored."""
    make_user(email="owner@x.io", phone="09120000003")
    token = _signup_otp_token("09120000003")
    resp = _client().post(
        "/api/v1/onboarding/signup",
        {
            "email": "different@x.io",  # ignored — phone wins
            "password": "pw-123456",
            "full_name": "Someone",
            "business_name": "Another Biz",
            "subdomain": "anotherbiz",
            "phone": "09120000003",
            "otp_token": token,
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("login") is True
    assert "access" in body
    assert User.objects.filter(phone="09120000003").count() == 1  # no second account


def test_signup_new_phone_creates_account_and_logs_in():
    from apps.tenancy.models import Business

    token = _signup_otp_token("09120000004")
    resp = _client().post(
        "/api/v1/onboarding/signup",
        {
            "email": "new@x.io",
            "password": "pw-123456",
            "full_name": "New Owner",
            "business_name": "Brand New",
            "subdomain": "brandnew",
            "phone": "09120000004",
            "otp_token": token,
        },
        format="json",
    )
    try:
        assert resp.status_code == 201
        body = resp.json()
        assert "access" in body and body.get("schema") == "brandnew"
        assert User.objects.filter(phone="09120000004", email="new@x.io").exists()
    finally:
        from django.db import connection

        connection.set_schema_to_public()
        Business.objects.filter(schema_name="brandnew").delete(force_drop=True)
