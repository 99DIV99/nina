"""
PERMANENT GATE: tenant isolation (B1).

Proves a query in tenant A's context cannot read tenant B's data, under normal
and adversarial (forged host) requests. This suite must pass in CI forever.
"""

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.booking.models import Customer

pytestmark = pytest.mark.django_db(transaction=True)


def test_data_does_not_cross_schemas(two_tenants):
    alpha, beta = two_tenants

    with tenant_context(alpha):
        Customer.objects.create(name="Alice", email="alice@alpha.io")
    with tenant_context(beta):
        Customer.objects.create(name="Bob", email="bob@beta.io")

    with tenant_context(alpha):
        names = set(Customer.objects.values_list("name", flat=True))
        assert names == {"Alice"}
        assert not Customer.objects.filter(name="Bob").exists()

    with tenant_context(beta):
        names = set(Customer.objects.values_list("name", flat=True))
        assert names == {"Bob"}
        assert not Customer.objects.filter(name="Alice").exists()


def test_forged_host_cannot_reach_another_tenants_data(two_tenants):
    """An adversary pointing Host at alpha gets alpha's app; nothing leaks beta."""
    alpha, beta = two_tenants
    with tenant_context(beta):
        Customer.objects.create(name="BetaSecret", email="secret@beta.io")

    client = Client()
    # Public services endpoint resolves the tenant purely from the host header.
    resp = client.get("/api/v1/public/services", HTTP_HOST="alpha.localhost")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "BetaSecret" not in body  # beta data must never appear under alpha's host


def test_unknown_host_is_rejected(two_tenants):
    client = Client()
    resp = client.get("/api/v1/public/services", HTTP_HOST="does-not-exist.localhost")
    # No tenant resolves -> django-tenants returns 404 (no schema), never another's data.
    assert resp.status_code in (404, 400)
