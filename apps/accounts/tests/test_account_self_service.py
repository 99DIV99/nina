"""Owner account self-service: phone+password login, OTP password reset, and
OTP-verified phone change.

The classic (credential) login uses phone + password now; the passwordless SMS
flow stays the primary. Password reset and phone change are gated by an OTP
verification token (the same signed-token mechanism sign-up uses).
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role
from apps.otp.services import make_verification_token
from conftest import add_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)

DASH = "dash.localhost"


@pytest.fixture(autouse=True)
def _reset_throttle():
    """The auth scope is 10/min; clear it so it doesn't bleed across tests."""
    from django.core.cache import cache

    cache.clear()


def _client(user=None) -> APIClient:
    client = APIClient()
    if user is not None:
        access = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_HOST=DASH)
    else:
        client.credentials(HTTP_HOST=DASH)
    return client


# --- phone + password login -------------------------------------------------


def test_phone_password_login_succeeds():
    make_user(email="p@test.io", password="pw-123456", phone="09120000020")
    resp = _client().post(
        "/api/v1/auth/login", {"phone": "09120000020", "password": "pw-123456"}, format="json"
    )
    assert resp.status_code == 200
    assert "access" in resp.json()


def test_phone_password_login_rejects_wrong_password():
    make_user(email="p2@test.io", password="pw-123456", phone="09120000021")
    resp = _client().post(
        "/api/v1/auth/login", {"phone": "09120000021", "password": "nope"}, format="json"
    )
    assert resp.status_code == 400


# --- password reset (OTP) ---------------------------------------------------


def test_password_reset_sets_new_password():
    make_user(email="r@test.io", password="old-123456", phone="09120000030")
    token = make_verification_token("09120000030", "password_reset")
    resp = _client().post(
        "/api/v1/auth/password/reset",
        {"phone": "09120000030", "otp_token": token, "password": "new-123456"},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.json()

    old = _client().post(
        "/api/v1/auth/login", {"phone": "09120000030", "password": "old-123456"}, format="json"
    )
    assert old.status_code == 400
    new = _client().post(
        "/api/v1/auth/login", {"phone": "09120000030", "password": "new-123456"}, format="json"
    )
    assert new.status_code == 200


def test_password_reset_requires_valid_token():
    make_user(email="r2@test.io", password="old-123456", phone="09120000031")
    resp = _client().post(
        "/api/v1/auth/password/reset",
        {"phone": "09120000031", "otp_token": "bogus", "password": "new-123456"},
        format="json",
    )
    assert resp.status_code == 400


# --- change phone (OTP on the new number) -----------------------------------


def test_change_phone_updates_number():
    user = make_user(email="c@test.io", password="pw-123456", phone="09120000040")
    token = make_verification_token("09120000041", "phone_change")
    resp = _client(user).post(
        "/api/v1/auth/phone", {"phone": "09120000041", "otp_token": token}, format="json"
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.phone == "09120000041"


def test_change_phone_rejects_taken_number():
    user = make_user(email="c1@test.io", password="pw-123456", phone="09120000050")
    make_user(email="c2@test.io", password="pw-123456", phone="09120000051")
    token = make_verification_token("09120000051", "phone_change")
    resp = _client(user).post(
        "/api/v1/auth/phone", {"phone": "09120000051", "otp_token": token}, format="json"
    )
    assert resp.status_code == 409


def test_change_phone_requires_verified_new_number():
    user = make_user(email="c3@test.io", password="pw-123456", phone="09120000060")
    resp = _client(user).post(
        "/api/v1/auth/phone", {"phone": "09120000061", "otp_token": "bogus"}, format="json"
    )
    assert resp.status_code == 400


# --- edit subdomain (owner, dashboard host) ---------------------------------


def test_change_subdomain_swaps_primary_domain(tenant_factory):
    from apps.tenancy.models import Domain

    biz = tenant_factory(name="Sub", schema="t_sub", subdomain="oldsub")
    user = make_user(email="own@sub.io", phone="09120000070")
    add_member(user, biz, role=Role.OWNER)

    resp = _client(user).post("/api/v1/context/subdomain", {"subdomain": "newsub"}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["subdomain"] == "newsub"
    assert Domain.objects.filter(tenant=biz, is_primary=True, domain="newsub.localhost").exists()


def test_change_subdomain_rejects_reserved(tenant_factory):
    biz = tenant_factory(name="Sub2", schema="t_sub2", subdomain="oldsub2")
    user = make_user(email="own2@sub.io", phone="09120000071")
    add_member(user, biz, role=Role.OWNER)

    resp = _client(user).post("/api/v1/context/subdomain", {"subdomain": "www"}, format="json")
    assert resp.status_code == 400
