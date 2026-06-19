"""Public business endpoint (F5 support): unauthenticated branding/vocabulary."""
import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.business.models import BusinessProfile

pytestmark = pytest.mark.django_db(transaction=True)


def test_public_business_returns_safe_branding(tenant):
    with tenant_context(tenant):
        profile = BusinessProfile.get_solo()
        profile.display_name = "Book & Co"
        profile.timezone = "Europe/London"
        profile.vocabulary = {"customer": "guest"}
        profile.save()

    client = APIClient()
    resp = client.get("/api/v1/public/business", HTTP_HOST="book.localhost")

    assert resp.status_code == 200
    data = resp.json()
    assert data["branding"]["displayName"] == "Book & Co"
    assert data["policies"]["timezone"] == "Europe/London"
    # Business-type default merged with the per-tenant override.
    assert data["vocabulary"]["customer"] == "guest"
    # No PII / authenticated fields leak through the public payload.
    assert "user" not in data
    assert "enabledModules" not in data
