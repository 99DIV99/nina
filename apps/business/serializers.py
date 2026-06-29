import re

from rest_framework import serializers

from apps.business.models import BusinessProfile

# Curated public-page channels (toggle + handle). Empty value == hidden.
ALLOWED_CHANNELS = ("telegram", "instagram", "x", "whatsapp", "website", "phone")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = (
            "display_name",
            "logo_url",
            "primary_color",
            "accent_color",
            "vocabulary",
            "timezone",
            "booking_lead_minutes",
            "max_advance_days",
            "cancellation_window_hours",
            "require_phone_otp",
            "updated_at",
        )
        read_only_fields = ("updated_at",)


class PageSettingsSerializer(serializers.ModelSerializer):
    """The 'Your Page' editor surface: template + content + branding + location.
    Scheduling/security policies stay on BusinessProfileSerializer (Settings)."""

    # Effective logo to preview (uploaded image if present, else the pasted URL).
    logo = serializers.SerializerMethodField()

    class Meta:
        model = BusinessProfile
        fields = (
            "template",
            "description",
            "cover_image_url",
            "address",
            "channels",
            "show_services",
            "show_hours",
            "accepting_bookings",
            "display_name",
            "logo",
            "logo_url",
            "primary_color",
            "accent_color",
            "latitude",
            "longitude",
            "updated_at",
        )
        read_only_fields = ("logo", "updated_at")

    def get_logo(self, obj) -> str:
        return obj.logo_display_url

    def validate_template(self, value):
        # Format-only: the frontend owns the template registry (slug -> component).
        value = (value or "").strip().lower()
        if not value or len(value) > 64 or not _SLUG_RE.match(value):
            raise serializers.ValidationError("Invalid template.")
        return value

    def validate_channels(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("channels must be an object.")
        cleaned = {}
        for key, raw in value.items():
            if key not in ALLOWED_CHANNELS:
                raise serializers.ValidationError(f"Unknown channel '{key}'.")
            text = str(raw or "").strip()
            if text:  # empty == hidden, so drop it
                cleaned[key] = text[:200]
        return cleaned
