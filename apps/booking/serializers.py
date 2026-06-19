from rest_framework import serializers

from apps.booking.models import Appointment, BusinessHours, Customer, Service, StaffMember, TimeOff


class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffMember
        fields = ("id", "name", "email", "timezone", "is_active", "user_id")


class ServiceSerializer(serializers.ModelSerializer):
    staff = serializers.PrimaryKeyRelatedField(
        many=True, queryset=StaffMember.objects.all(), required=False
    )

    class Meta:
        model = Service
        fields = (
            "id",
            "name",
            "description",
            "duration_minutes",
            "buffer_before_minutes",
            "buffer_after_minutes",
            "price",
            "is_active",
            "staff",
        )


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone", "notes", "created_at")
        read_only_fields = ("created_at",)


class BusinessHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = ("id", "staff", "weekday", "start_time", "end_time")

    def validate(self, attrs):
        start = attrs.get("start_time")
        end = attrs.get("end_time")
        if start and end and end <= start:
            raise serializers.ValidationError("end_time must be after start_time.")
        return attrs


class TimeOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOff
        fields = ("id", "staff", "start_at", "end_at", "reason")

    def validate(self, attrs):
        if attrs["end_at"] <= attrs["start_at"]:
            raise serializers.ValidationError("end_at must be after start_at.")
        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = (
            "id",
            "service",
            "staff",
            "customer",
            "start_at",
            "end_at",
            "status",
            "price",
            "source",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("end_at", "status", "created_at", "updated_at")


class AppointmentCreateSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all())
    staff = serializers.PrimaryKeyRelatedField(queryset=StaffMember.objects.all())
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    start_at = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    # Staff override for walk-ins / out-of-hours manual bookings.
    override_availability = serializers.BooleanField(required=False, default=False)
    price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )


class RescheduleSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
    override_availability = serializers.BooleanField(required=False, default=False)


class AvailabilityQuerySerializer(serializers.Serializer):
    service = serializers.IntegerField()
    staff = serializers.IntegerField(required=False)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
