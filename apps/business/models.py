"""
Per-tenant business configuration (B3): branding + vocabulary.

The Business (tenant) row with its feature flags lives in the PUBLIC schema
(apps.tenancy.Business). This module holds the per-schema, editable presentation
config. It is a singleton per tenant schema.
"""

from django.db import models

# Template chosen by a business is stored as a plain slug value (the frontend owns
# the actual skins + a slug->component registry, so new templates never need a
# model change/migration). Unknown slug -> frontend falls back to this default.
DEFAULT_PAGE_TEMPLATE = "spotlight"


class BusinessProfile(models.Model):
    """Singleton (one row) per tenant schema. Branding + vocabulary."""

    # Branding
    display_name = models.CharField(max_length=200, blank=True)
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=9, default="#111827")
    accent_color = models.CharField(max_length=9, default="#2563eb")

    # ---- Public page ("Your Page") -------------------------------------------
    # A chosen template (frontend skin, by slug) over the editable content below;
    # services/hours/map are pulled from their real home, not duplicated here.
    template = models.CharField(max_length=64, default=DEFAULT_PAGE_TEMPLATE)
    description = models.CharField(max_length=200, blank=True)  # tagline under the title
    cover_image_url = models.URLField(blank=True)
    # Curated channel links, e.g. {"telegram": "@h", "instagram": "h", "website": "..."}.
    # Allowed keys: telegram, instagram, x, whatsapp, website, phone. Empty = hidden.
    channels = models.JSONField(default=dict, blank=True)
    show_services = models.BooleanField(default=True)
    show_hours = models.BooleanField(default=True)
    # Owner-controlled "Accepting online bookings" switch. OFF => the public page
    # shows a friendly closed message; the panel + manual bookings keep working.
    # Distinct from operator suspension (tenancy.Business.is_active).
    accepting_bookings = models.BooleanField(default=True)

    # Vocabulary overrides, e.g. {"customer": "patient", "appointment": "visit"}
    vocabulary = models.JSONField(default=dict, blank=True)

    # Policy knobs surfaced to the booking layer / frontend.
    timezone = models.CharField(max_length=64, default="UTC")
    booking_lead_minutes = models.PositiveIntegerField(default=60)
    max_advance_days = models.PositiveIntegerField(default=60)
    cancellation_window_hours = models.PositiveIntegerField(default=24)

    # Require the customer to verify their phone (SMS OTP) before a public booking.
    # Secure by default; a business can opt out in Settings.
    require_phone_otp = models.BooleanField(default=True)

    # Geographic location (so customers can find the business on a map). Required
    # at sign-up via the API; nullable at the DB so pre-existing rows stay valid.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

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
