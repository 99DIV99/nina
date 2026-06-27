"""
Onboarding orchestration (B3): sign up -> pick type -> claim subdomain ->
seed first service/hours/staff -> return a 'you're live' link.

Runs in the PUBLIC schema, then enters the freshly created tenant schema to seed.
"""

import logging

from django.conf import settings
from django.db import transaction
from django_tenants.utils import tenant_context

from apps.accounts.models import Membership, Role, User
from apps.common.exceptions import DomainError
from apps.tenancy.models import Business, BusinessType
from apps.tenancy.provisioning import create_business

logger = logging.getLogger("nina.onboarding")


@transaction.atomic
def onboard(
    *,
    email: str,
    password: str,
    business_name: str,
    subdomain: str,
    business_type: str = BusinessType.GENERAL,
    phone: str = "",
    first_name: str = "",
    last_name: str = "",
    full_name: str = "",
    latitude=None,
    longitude=None,
) -> dict:
    """Create owner account + tenant + seed. Returns a summary with the live link."""
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        raise DomainError("An account with that email already exists.", code="email_taken")

    full_name = full_name or f"{first_name} {last_name}".strip()
    business = create_business(name=business_name, subdomain=subdomain, business_type=business_type)

    owner = User.objects.create_user(
        email=email,
        password=password,
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        is_phone_verified=bool(phone),
    )
    Membership.objects.create(user=owner, business=business, role=Role.OWNER, is_active=True)

    _seed_tenant(business, owner_full_name=full_name, latitude=latitude, longitude=longitude)

    primary = business.domains.filter(is_primary=True).first()
    live_url = f"https://{primary.domain}" if primary else None
    logger.info("onboarded", extra={"tenant": business.schema_name})
    return {
        "business_id": business.id,
        "schema": business.schema_name,
        "subdomain": subdomain.lower(),
        "live_url": live_url,
        "owner_email": owner.email,
    }


def _seed_tenant(
    business: Business, *, owner_full_name: str, latitude=None, longitude=None
) -> None:
    """Seed the tenant schema with a profile, one staff member, a service, and hours."""
    from apps.booking.models import BusinessHours, Service, StaffMember
    from apps.business.models import DEFAULT_VOCABULARY, BusinessProfile

    with tenant_context(business):
        profile = BusinessProfile.get_solo()
        profile.display_name = business.name
        profile.vocabulary = DEFAULT_VOCABULARY.get(
            business.experience, DEFAULT_VOCABULARY["general"]
        )
        profile.latitude = latitude
        profile.longitude = longitude
        profile.save()

        staff = StaffMember.objects.create(name=owner_full_name or "Owner", is_active=True)
        service = Service.objects.create(
            name="Standard appointment",
            duration_minutes=30,
            price="0.00",
            is_active=True,
        )
        service.staff.add(staff)

        # Mon–Fri 09:00–17:00 default availability.
        for weekday in range(0, 5):
            BusinessHours.objects.create(
                staff=staff, weekday=weekday, start_time="09:00", end_time="17:00"
            )


def reserved_subdomains() -> set[str]:
    return set(settings.RESERVED_SUBDOMAINS)
