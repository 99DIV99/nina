"""
Booking engine models (B4) -- per-tenant schema.

Correctness rules (non-negotiable):
- Double-booking is prevented at the DATABASE level with a PostgreSQL exclusion
  constraint on (staff, [start_at, end_at)) for active appointments, in addition
  to an atomic booking transaction.
- All datetimes are stored timezone-aware in UTC (USE_TZ=True). Availability is
  computed in the staff/business local timezone and converted to UTC.
"""
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Func, Q


class TsTzRange(Func):
    """SQL tstzrange(start, end, '[)') for the exclusion constraint."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()

    def __init__(self, lower, upper, bounds="[)"):
        super().__init__(lower, upper, models.Value(bounds))


class Service(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    buffer_before_minutes = models.PositiveIntegerField(default=0)
    buffer_after_minutes = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    staff = models.ManyToManyField("StaffMember", related_name="services", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_service"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class StaffMember(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    # Optional link to a platform user (public schema) by id -- no cross-schema FK.
    user_id = models.BigIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_staff"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_customer"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class BusinessHours(models.Model):
    """Recurring weekly availability per staff member (local time)."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="hours")
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        db_table = "booking_business_hours"
        ordering = ("staff", "weekday", "start_time")

    def __str__(self) -> str:
        return f"{self.staff} {self.get_weekday_display()} {self.start_time}-{self.end_time}"


class TimeOff(models.Model):
    """One-off unavailability (vacation, sick, blocked) -- UTC datetimes."""

    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="time_off")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "booking_time_off"
        ordering = ("start_at",)

    def __str__(self) -> str:
        return f"{self.staff} off {self.start_at}–{self.end_at}"


class AppointmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No-show"


# Statuses that occupy a slot (block other bookings).
ACTIVE_STATUSES = [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]


class Appointment(models.Model):
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="appointments")
    staff = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="appointments")
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments"
    )

    # Stored UTC; spans the service duration PLUS buffers (the bookable block).
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    status = models.CharField(
        max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.PENDING
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Provenance: who created it (staff panel, public page, or a bot).
    source = models.CharField(max_length=20, default="panel")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "booking_appointment"
        ordering = ("start_at",)
        indexes = [
            models.Index(fields=["staff", "start_at"]),
            models.Index(fields=["status", "start_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(end_at__gt=models.F("start_at")), name="appt_end_after_start"
            ),
            # The hard guarantee: no two ACTIVE appointments for the same staff
            # may overlap in time. Enforced by Postgres, immune to race conditions.
            ExclusionConstraint(
                name="no_double_booking",
                expressions=[
                    ("staff", RangeOperators.EQUAL),
                    (TsTzRange("start_at", "end_at"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=ACTIVE_STATUSES),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service} w/ {self.staff} @ {self.start_at} [{self.status}]"
