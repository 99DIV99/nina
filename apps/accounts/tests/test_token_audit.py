"""
JWT token audit: issued refresh tokens are recorded (and revocable).

With `rest_framework_simplejwt.token_blacklist` installed, every refresh token
minted at login writes an OutstandingToken (jti, created_at, expires_at) in the
public schema — so tokens can be listed, inspected, and blacklisted.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from conftest import make_user

pytestmark = pytest.mark.django_db(transaction=True)


def test_login_records_an_outstanding_token():
    user = make_user(email="solo@test.io", password="pw-123456", phone="09120000001")
    before = OutstandingToken.objects.count()

    resp = APIClient().post(
        "/api/v1/auth/login",
        {"phone": "09120000001", "password": "pw-123456"},
        format="json",
        HTTP_HOST="dash.localhost",
    )

    assert resp.status_code == 200
    assert OutstandingToken.objects.count() == before + 1

    token = OutstandingToken.objects.latest("id")
    assert token.user_id == user.id
    assert token.expires_at is not None  # we can see when it expires
