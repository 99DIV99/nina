"""
Per-tenant business configuration (B3): branding + vocabulary.

The Business (tenant) row with its feature flags lives in the PUBLIC schema
(apps.tenancy.Business). This module holds the per-schema, editable presentation
config. It is a singleton per tenant schema.
"""
from django.db import models


class BusinessProfile(models.Model):
    """Singleton (one row) per tenant schema. Branding + vocabulary."""

    # Branding
    display_name = models.CharField(max_length=200, blank=True)
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=9, default="#111827")
    accent_color = models.CharField(max_length=9, default="#2563eb")

    # Vocabulary overrides, e.g. {"customer": "patient", "appointment": "visit"}
    vocabulary = models.JSONField(default=dict, blank=True)

    # Policy knobs surfaced to the booking layer / frontend.
    timezone = models.CharField(max_length=64, default="UTC")
    booking_lead_minutes = models.PositiveIntegerField(default=60)
    max_advance_days = models.PositiveIntegerField(default=60)
    cancellation_window_hours = models.PositiveIntegerField(default=24)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_profile"

    def __str__(self) -> str:
        return self.display_name or "BusinessProfile"

    @classmethod
    def get_solo(cls) -> "BusinessProfile":
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


DEFAULT_VOCABULARY = {
    "barber": {"customer": "client", "appointment": "appointment", "staff": "barber"},
    "clinic": {"customer": "patient", "appointment": "visit", "staff": "practitioner"},
    "general": {"customer": "customer", "appointment": "appointment", "staff": "staff"},
}
