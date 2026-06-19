from rest_framework import serializers

from apps.business.models import BusinessProfile


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
            "updated_at",
        )
        read_only_fields = ("updated_at",)
