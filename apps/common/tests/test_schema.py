"""Smoke test: the OpenAPI schema (and therefore /api/docs/) must render.

Most endpoints are hand-written ``APIView``s annotated with ``@extend_schema``;
a bad annotation only surfaces at runtime on the docs page, not in unit tests.
This renders both the public (dashboard/apex) and tenant schema documents so CI
fails loudly instead of shipping a broken docs page.
"""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db(transaction=True)


def test_public_schema_renders():
    """The public host (dashboard/apex) serves the public-schema API docs."""
    client = APIClient()
    client.credentials(HTTP_HOST="dash.localhost")
    resp = client.get("/api/schema/")
    assert resp.status_code == 200
    assert b"openapi" in resp.content


def test_tenant_schema_renders(tenant_factory):
    """A tenant host serves the per-tenant booking/accounting/bot API docs."""
    tenant_factory(name="DocTest", schema="t_docs", subdomain="docs")
    client = APIClient()
    client.credentials(HTTP_HOST="docs.localhost")
    resp = client.get("/api/schema/")
    assert resp.status_code == 200
    assert b"openapi" in resp.content
