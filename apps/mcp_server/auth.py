"""MCP internal authentication - token generation and validation."""

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.authorization import effective_permissions, current_membership
from apps.mcp_server.models import MCPInternalToken


def generate_internal_token(request, expires_seconds=300):
    """Generate an internal MCP token for the current user and tenant.

    Args:
        request: Django request with authenticated user
        expires_seconds: Token lifetime (default 5 minutes)

    Returns:
        MCPInternalToken instance
    """
    membership = current_membership(request)
    if not membership:
        raise PermissionDenied("User is not a member of this tenant")

    # Get user's effective permissions
    permissions = effective_permissions(request)

    # Generate token
    token = MCPInternalToken.generate(
        tenant=membership.business,
        user=request.user,
        scopes=list(permissions),
        expires_seconds=expires_seconds,
    )

    return token


def validate_internal_token(token_string):
    """Validate an internal MCP token and return tenant + user + scopes.

    Args:
        token_string: The token string from X-MCP-Token header

    Returns:
        tuple: (token, tenant, user, scopes)

    Raises:
        PermissionDenied: If token is invalid or expired
    """
    try:
        token = MCPInternalToken.objects.select_related(
            "tenant", "user"
        ).get(token=token_string)
    except MCPInternalToken.DoesNotExist:
        raise PermissionDenied("Invalid token")

    if not token.is_valid():
        raise PermissionDenied("Token expired or revoked")

    # Mark as used
    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])

    return token, token.tenant, token.user, token.scopes


def has_permission(scopes, required_permission):
    """Check if a permission is in the scopes list.

    Args:
        scopes: List of permission strings
        required_permission: Permission to check

    Returns:
        bool: True if permission is granted
    """
    return required_permission in scopes
