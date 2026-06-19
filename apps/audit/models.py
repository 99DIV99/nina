"""Per-tenant audit log for sensitive actions (B2 / B10)."""

from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        PERMISSION_CHANGE = "permission_change", "Permission change"
        RECORD_ACCESS = "record_access", "Record access"
        IMPERSONATION = "impersonation", "Impersonation"
        BOOKING_OVERRIDE = "booking_override", "Booking override"
        DATA_EXPORT = "data_export", "Data export"

    action = models.CharField(max_length=40, choices=Action.choices)
    # We store the acting user id (from the public schema) without an FK so the
    # per-tenant table never reaches across schemas.
    actor_user_id = models.BigIntegerField(null=True, blank=True)
    actor_email = models.EmailField(blank=True)
    target = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_email or self.actor_user_id} @ {self.created_at}"
