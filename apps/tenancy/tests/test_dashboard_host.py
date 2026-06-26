"""
PERMANENT GATE: dashboard-host tenant resolution.

The unified business panel is served from a single host (e.g. dash.ninax.net)
with no tenant in the URL. On that host the active business is resolved from the
authenticated user's membership in the PUBLIC schema (floor 0), NOT the hostname.

These tests prove:
- a request on the dashboard host reaches the user's OWN business schema, and
  never another business's data;
- removing the membership (or omitting the token) drops the request back to the
  public schema, so no panel data is reachable;
- the booking subdomains keep host-based resolution (unchanged).
"""

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role
from apps.booking.models import Customer
from conftest import add_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)

DASH = "dash.localhost"  # matches NINA_DASHBOARD_HOSTS default in settings


def dash_client(user):
    """An API client whose vanilla (no `biz` claim) token is sent to the dash host."""
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_HOST=DASH)
    return client


def _seed_customers(alpha, beta):
    with tenant_context(alpha):
        Customer.objects.create(name="AlphaCust", phone="100")
    with tenant_context(beta):
        Customer.objects.create(name="BetaCust", phone="200")


def test_login_on_dashboard_issues_token(two_tenants):
    """Login works on the dash host (public schema) and returns a usable token —
    the business is not needed in the token; it's resolved per-request."""
    alpha, _ = two_tenants
    user = make_user(email="owner@alpha.io", password="pw-123456")
    add_member(user, alpha, role=Role.OWNER)

    resp = APIClient().post(
        "/api/v1/auth/login",
        {"email": "owner@alpha.io", "password": "pw-123456"},
        format="json",
        HTTP_HOST=DASH,
    )
    assert resp.status_code == 200
    assert "access" in resp.json()


def test_dashboard_resolves_tenant_from_user(two_tenants):
    """alpha's owner, on the dash host, sees ALPHA's customers and never beta's."""
    alpha, beta = two_tenants
    _seed_customers(alpha, beta)

    user = make_user(email="owner@alpha.io")
    add_member(user, alpha, role=Role.OWNER)

    resp = dash_client(user).get("/api/v1/booking/customers")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "AlphaCust" in body
    assert "BetaCust" not in body  # cross-tenant data must never appear


def test_dashboard_user_only_sees_own_business(two_tenants):
    """beta's owner, same host, resolves to BETA — proving it's the user, not the host."""
    alpha, beta = two_tenants
    _seed_customers(alpha, beta)

    user = make_user(email="owner@beta.io")
    add_member(user, beta, role=Role.OWNER)

    resp = dash_client(user).get("/api/v1/booking/customers")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "BetaCust" in body
    assert "AlphaCust" not in body


def test_dashboard_without_token_stays_public(two_tenants):
    """No token -> public schema -> panel endpoints don't exist there -> not reachable."""
    client = APIClient()
    client.credentials(HTTP_HOST=DASH)
    resp = client.get("/api/v1/booking/customers")
    assert resp.status_code in (401, 403, 404)


def test_inactive_membership_denied_on_dashboard(two_tenants):
    """A revoked membership resolves to no business -> public -> no panel data."""
    alpha, _ = two_tenants
    user = make_user(email="ex@alpha.io")
    membership = add_member(user, alpha, role=Role.OWNER)
    membership.is_active = False
    membership.save()

    resp = dash_client(user).get("/api/v1/booking/customers")
    assert resp.status_code in (401, 403, 404)


def test_subdomain_host_still_resolves_by_host(two_tenants):
    """Regression: booking subdomains keep host-based resolution (delegates to upstream)."""
    alpha, beta = two_tenants
    _seed_customers(alpha, beta)

    user = make_user(email="owner@alpha.io")
    add_member(user, alpha, role=Role.OWNER)

    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_HOST="alpha.localhost")
    resp = client.get("/api/v1/booking/customers")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "AlphaCust" in body
    assert "BetaCust" not in body
