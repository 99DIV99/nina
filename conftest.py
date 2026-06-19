"""
Pytest fixtures for the multi-tenant test suite.

django-tenants needs real schemas, so tenant-creating tests run with
`transaction=True` (no outer wrapping transaction) and we create/drop schemas
explicitly. Fixtures here build isolated tenants A and B for the isolation suite.
"""

import pytest
from django.db import connection

from apps.accounts.models import Membership, Role, User
from apps.tenancy.models import Business, BusinessType, Domain


def _make_tenant(
    name: str, schema: str, subdomain: str, business_type=BusinessType.BARBER
) -> Business:
    existing = Business.objects.filter(schema_name=schema).first()
    if existing:
        existing.delete(force_drop=True)
    business = Business(name=name, schema_name=schema, business_type=business_type)
    business.apply_type_defaults()
    business.save()  # creates the schema + runs tenant migrations
    Domain.objects.create(domain=f"{subdomain}.localhost", tenant=business, is_primary=True)
    return business


@pytest.fixture
def tenant_factory(transactional_db):
    created: list[Business] = []

    def make(name="Tenant", schema="t_test", subdomain="ttest", business_type=BusinessType.BARBER):
        business = _make_tenant(name, schema, subdomain, business_type)
        created.append(business)
        return business

    yield make

    connection.set_schema_to_public()
    for business in created:
        try:
            business.delete(force_drop=True)
        except Exception:
            pass


@pytest.fixture
def two_tenants(tenant_factory):
    a = tenant_factory(name="Alpha", schema="t_alpha", subdomain="alpha")
    b = tenant_factory(name="Beta", schema="t_beta", subdomain="beta")
    return a, b


def make_user(email="user@test.io", password="pw-123456", **extra) -> User:
    User.objects.filter(email=email).delete()
    return User.objects.create_user(email=email, password=password, **extra)


def add_member(user: User, business: Business, role=Role.OWNER) -> Membership:
    return Membership.objects.create(user=user, business=business, role=role, is_active=True)
