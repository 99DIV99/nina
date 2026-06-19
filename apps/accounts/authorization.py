"""
Server-side authorization (SECURITY).

Everything here re-derives identity from our own data. The client supplies an
authenticated User (via JWT/session) and a host (which resolves to a tenant). We
NEVER read a role, tenant, type, or permission claim from the request body.

`current_membership(request)` is the single choke point: given the authenticated
user and the tenant resolved from the host, it returns the active Membership or
None. From the membership we derive the role; from the role we derive permissions.
"""

from __future__ import annotations

from django.db import connection

from apps.accounts.models import Membership, Role

# --- Permission catalogue -------------------------------------------------
P_BOOKING_VIEW = "booking.view"
P_BOOKING_MANAGE = "booking.manage"
P_CUSTOMER_VIEW = "customer.view"
P_CUSTOMER_MANAGE = "customer.manage"
P_SERVICE_MANAGE = "service.manage"
P_STAFF_MANAGE = "staff.manage"
P_ACCOUNTING_VIEW = "accounting.view"
P_ACCOUNTING_MANAGE = "accounting.manage"
P_RECORDS_VIEW = "records.view"
P_BOTS_MANAGE = "bots.manage"
P_SETTINGS_MANAGE = "settings.manage"
P_BILLING_MANAGE = "billing.manage"

_ALL = {
    P_BOOKING_VIEW,
    P_BOOKING_MANAGE,
    P_CUSTOMER_VIEW,
    P_CUSTOMER_MANAGE,
    P_SERVICE_MANAGE,
    P_STAFF_MANAGE,
    P_ACCOUNTING_VIEW,
    P_ACCOUNTING_MANAGE,
    P_RECORDS_VIEW,
    P_BOTS_MANAGE,
    P_SETTINGS_MANAGE,
    P_BILLING_MANAGE,
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.OWNER: set(_ALL),
    Role.FRONT_DESK: {
        P_BOOKING_VIEW,
        P_BOOKING_MANAGE,
        P_CUSTOMER_VIEW,
        P_CUSTOMER_MANAGE,
        P_SERVICE_MANAGE,
        P_ACCOUNTING_VIEW,
    },
    Role.PRACTITIONER: {
        P_BOOKING_VIEW,
        P_BOOKING_MANAGE,
        P_CUSTOMER_VIEW,
        P_RECORDS_VIEW,
    },
}


def permissions_for_role(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def current_business(request):
    """The tenant Business resolved from the host by TenantMainMiddleware.

    Returns None in the public schema (no tenant active)."""
    tenant = getattr(request, "tenant", None)
    if tenant is None or getattr(connection, "schema_name", "public") == "public":
        return None
    return tenant


def current_membership(request) -> Membership | None:
    """The authenticated user's ACTIVE membership in the CURRENT tenant, or None.

    This is the only place that links a user to a tenant role. A forged body
    claiming a role/tenant cannot influence this -- we query Membership by the
    server-resolved (user, tenant) pair.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    business = current_business(request)
    if business is None:
        return None
    return (
        Membership.objects.select_related("business")
        .filter(user=user, business=business, is_active=True)
        .first()
    )


def effective_permissions(request) -> set[str]:
    membership = current_membership(request)
    if membership is None:
        return set()
    perms = permissions_for_role(membership.role)
    # Feature flags gate permissions: you cannot have accounting perms if the
    # tenant has no accounting module, regardless of role.
    business = membership.business
    if not business.has_accounting:
        perms.discard(P_ACCOUNTING_VIEW)
        perms.discard(P_ACCOUNTING_MANAGE)
    if not business.has_records:
        perms.discard(P_RECORDS_VIEW)
    if not business.has_bots:
        perms.discard(P_BOTS_MANAGE)
    return perms
