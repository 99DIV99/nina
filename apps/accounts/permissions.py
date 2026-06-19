"""DRF permission classes that enforce the authorization layer on every endpoint."""
from rest_framework.permissions import BasePermission

from apps.accounts.authorization import current_membership, effective_permissions


class IsTenantMember(BasePermission):
    """User must be authenticated AND have an active membership in the resolved
    tenant. This denies cross-tenant access even with a valid token for a
    different tenant."""

    message = "You are not a member of this business."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return current_membership(request) is not None


class HasPermission(IsTenantMember):
    """Require a specific permission string. Set `required_permission` on the view,
    or `required_permissions` (all required)."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        required = set()
        single = getattr(view, "required_permission", None)
        if single:
            required.add(single)
        required.update(getattr(view, "required_permissions", []) or [])
        if not required:
            return True
        granted = effective_permissions(request)
        return required.issubset(granted)


class IsPlatformOperator(BasePermission):
    """Platform staff only (operator console). Tenant role is irrelevant here."""

    message = "Platform operator access required."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
