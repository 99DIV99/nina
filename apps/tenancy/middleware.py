"""
Tenant resolution that supports a central dashboard host.

Two ways a request names its tenant:

1. Tenant host (e.g. ``sadra.ninax.net``) — the client-facing booking surface.
   Resolved from the ``Domain`` table by hostname, exactly like upstream
   django-tenants. Unchanged.

2. Dashboard host (``dash.ninax.net``) — the unified business panel, shared by
   every business. There is no tenant in the hostname, so we resolve the active
   business from the PUBLIC schema's directory (``Membership``): the token only
   carries the user's identity (a vanilla JWT), and we ask floor 0 which
   business that user belongs to. With one business per account this is
   unambiguous, costs a single query, and auto-follows membership changes (no
   stale claim to re-issue). Unauthenticated requests (login, refresh, signup)
   stay in the public schema, where those endpoints live.

This single membership lookup is also the security boundary: it both *finds*
the business and proves the user is an active member of it, so a request can
only ever reach a schema the user actually belongs to.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.db import connection
from django.http import HttpResponseNotFound
from django_tenants.middleware.main import TenantMainMiddleware as _BaseTenantMiddleware
from django_tenants.utils import get_public_schema_name, get_tenant_model


class TenantMainMiddleware(_BaseTenantMiddleware):
    """Host-based tenant resolution, plus JWT-based resolution on the dashboard host."""

    def process_request(self, request):
        try:
            hostname = self.hostname_from_request(request)
        except DisallowedHost:
            return HttpResponseNotFound()

        if hostname not in settings.NINA_DASHBOARD_HOSTS:
            # Booking subdomains + apex: unchanged host-based resolution.
            return super().process_request(request)

        # Dashboard host: the tenant comes from the user (via floor 0), not the host.
        connection.set_schema_to_public()
        business = self._business_for_user(request) or self._public_tenant()
        business.domain_url = hostname
        request.tenant = business
        connection.set_tenant(business)
        self.setup_url_routing(request)

    @staticmethod
    def _public_tenant():
        return get_tenant_model().objects.get(schema_name=get_public_schema_name())

    @staticmethod
    def _business_for_user(request):
        """The active Business of the request's authenticated user, looked up in
        the public-schema directory (``Membership``). One business per account, so
        the first active membership is THE business. Returns None when there is no
        valid token or no membership (request then stays in the public schema)."""
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None

        # Decode + verify signature/expiry here; the view's DRF auth re-decodes
        # for request.user. A bad/expired token -> None -> public -> 401 downstream.
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import AccessToken

        try:
            token = AccessToken(auth[7:])
        except TokenError:
            return None

        user_id = token.get("user_id")
        if not user_id:
            return None

        # Membership + Business are SHARED_APPS — queried in the public schema.
        from apps.accounts.models import Membership

        membership = (
            Membership.objects.select_related("business")
            .filter(user_id=user_id, is_active=True, business__is_active=True)
            .order_by("id")
            .first()
        )
        return membership.business if membership else None
