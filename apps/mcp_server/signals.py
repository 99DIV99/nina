"""Celery beat tasks for MCP server maintenance."""

from celery import shared_task
from django.utils.timezone import now


@shared_task
def cleanup_expired_mcp_tokens():
    """Delete expired internal tokens."""
    from apps.mcp_server.models import MCPInternalToken

    deleted, _ = MCPInternalToken.objects.filter(
        expires_at__lt=now(),
        is_revoked=False,
    ).delete()
    return f"Deleted {deleted} expired tokens"


@shared_task
def cleanup_old_audit_logs():
    """Delete audit logs older than 30 days."""
    from apps.mcp_server.models import MCPRequestAudit

    from datetime import timedelta
    cutoff = now() - timedelta(days=30)

    deleted, _ = MCPRequestAudit.objects.filter(
        timestamp__lt=cutoff,
    ).delete()
    return f"Deleted {deleted} old audit logs"


@shared_task
def cleanup_used_tokens():
    """Delete used tokens (they're single-use)."""
    from apps.mcp_server.models import MCPInternalToken

    deleted, _ = MCPInternalToken.objects.filter(
        used_at__isnull=False,
        is_revoked=False,
    ).delete()
    return f"Deleted {deleted} used tokens"
