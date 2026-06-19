"""Helper to write audit entries from anywhere in a tenant request."""

from django.db import connection

from apps.audit.models import AuditLog


def record(action: str, *, actor=None, target: str = "", metadata: dict | None = None, ip=None):
    """Write an audit entry in the CURRENT tenant schema. No-op in public schema."""
    if getattr(connection, "schema_name", "public") == "public":
        return None
    return AuditLog.objects.create(
        action=action,
        actor_user_id=getattr(actor, "id", None),
        actor_email=getattr(actor, "email", "") or "",
        target=target,
        metadata=metadata or {},
        ip_address=ip,
    )
