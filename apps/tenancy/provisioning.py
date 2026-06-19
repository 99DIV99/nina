"""
Tenant provisioning service (B1).

create_business():
  1. validate + reserve the subdomain
  2. create the Business row -> django-tenants auto-creates the schema and runs
     tenant migrations
  3. create the primary Domain
  4. apply business-type feature-flag defaults

All wrapped so a failure does not leave a half-provisioned tenant.
"""
import logging

from django.conf import settings
from django.db import transaction

from apps.common.exceptions import DomainError
from apps.tenancy.models import Business, BusinessType, Domain
from apps.tenancy.subdomains import validate_subdomain

logger = logging.getLogger("nina.provisioning")


def schema_name_for(subdomain: str) -> str:
    # Postgres schema names: keep it derived from the subdomain but hyphen-free.
    return subdomain.replace("-", "_")


@transaction.atomic
def create_business(
    *,
    name: str,
    subdomain: str,
    business_type: str = BusinessType.GENERAL,
) -> Business:
    """Provision a new tenant. Raises DomainError on invalid/taken subdomain."""
    sub = validate_subdomain(subdomain)
    host = f"{sub}.{settings.BASE_DOMAIN}"

    if Domain.objects.filter(domain=host).exists():
        raise DomainError("That subdomain is already taken.", code="subdomain_taken")

    schema = schema_name_for(sub)
    if Business.objects.filter(schema_name=schema).exists():
        raise DomainError("That subdomain is already taken.", code="subdomain_taken")

    business = Business(
        name=name.strip(),
        schema_name=schema,
        business_type=business_type,
    )
    business.apply_type_defaults()
    # Saving triggers django-tenants schema creation + tenant migrations.
    business.save()

    Domain.objects.create(domain=host, tenant=business, is_primary=True, is_custom=False)

    logger.info(
        "tenant_provisioned",
        extra={"tenant": schema, "path": host, "method": "PROVISION"},
    )
    return business


@transaction.atomic
def add_custom_domain(business: Business, hostname: str, *, make_primary: bool = False) -> Domain:
    """Attach a custom domain to an existing tenant (B1 'later')."""
    hostname = hostname.strip().lower()
    if Domain.objects.filter(domain=hostname).exists():
        raise DomainError("That domain is already in use.", code="domain_taken")
    if make_primary:
        Domain.objects.filter(tenant=business, is_primary=True).update(is_primary=False)
    return Domain.objects.create(
        domain=hostname, tenant=business, is_primary=make_primary, is_custom=True
    )


def suspend(business: Business) -> None:
    from django.utils import timezone

    business.is_active = False
    business.suspended_at = timezone.now()
    business.save(update_fields=["is_active", "suspended_at"])


def reactivate(business: Business) -> None:
    business.is_active = True
    business.suspended_at = None
    business.save(update_fields=["is_active", "suspended_at"])
