"""
PERMANENT GATE: authorization (B2).

- cross-tenant access denied (member of A cannot act on B)
- role escalation denied (front_desk cannot perform owner-only writes)
- a forged "I'm a clinic" request gets no clinic data/permissions
"""
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership, Role
from apps.tenancy.models import BusinessType

from conftest import add_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)


def auth_client(user, host):
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_HOST=host)
    return client


def test_cross_tenant_access_denied(two_tenants):
    alpha, beta = two_tenants
    user = make_user(email="alpha-owner@test.io")
    add_member(user, alpha, role=Role.OWNER)  # member of alpha only

    # Same valid token, but pointed at beta's host -> not a member -> denied.
    client = auth_client(user, host="beta.localhost")
    resp = client.get("/api/v1/context/")
    assert resp.status_code == 403

    client_ok = auth_client(user, host="alpha.localhost")
    assert client_ok.get("/api/v1/context/").status_code == 200


def test_role_escalation_denied(two_tenants):
    alpha, _ = two_tenants
    user = make_user(email="frontdesk@test.io")
    add_member(user, alpha, role=Role.FRONT_DESK)

    client = auth_client(user, host="alpha.localhost")
    # front_desk lacks settings.manage -> cannot edit branding/policies.
    resp = client.patch("/api/v1/context/profile", {"display_name": "Hacked"}, format="json")
    assert resp.status_code == 403


def test_forged_clinic_claim_gets_no_clinic_data(two_tenants):
    """Alpha is a barber (has_records=False). A body claiming clinic/records must
    be ignored: the server re-derives modules/permissions from its own data."""
    alpha, _ = two_tenants
    assert alpha.business_type == BusinessType.BARBER
    user = make_user(email="owner2@test.io")
    add_member(user, alpha, role=Role.OWNER)

    client = auth_client(user, host="alpha.localhost")
    resp = client.get("/api/v1/context/", data={"business_type": "clinic", "has_records": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["experience"] == "barber"
    assert "records" not in body["enabledModules"]
    assert "records.view" not in body["user"]["permissions"]


def test_non_member_authenticated_user_denied(two_tenants):
    alpha, _ = two_tenants
    stranger = make_user(email="stranger@test.io")  # no membership anywhere
    client = auth_client(stranger, host="alpha.localhost")
    assert client.get("/api/v1/context/").status_code == 403
