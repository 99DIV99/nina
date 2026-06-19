"""Availability engine behaviour (B4): hours, buffers, time off, lead, advance."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django_tenants.utils import tenant_context

from apps.booking import services as booking_services
from apps.booking.availability import generate_slots
from apps.booking.models import TimeOff

from .conftest import build_staff_service

pytestmark = pytest.mark.django_db(transaction=True)
UTC = ZoneInfo("UTC")


def test_slots_respect_business_hours(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(tz="UTC", duration=60, start="09:00", end="12:00")
        slots = generate_slots(
            service=service, staff=staff,
            range_start=date(2026, 7, 6), range_end=date(2026, 7, 6),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        # 09:00-12:00 with 60-min duration, 15-min step -> starts 09:00..11:00.
        starts = [s.start.strftime("%H:%M") for s in slots]
        assert starts[0] == "09:00"
        assert starts[-1] == "11:00"
        assert "11:15" not in starts  # would end after 12:00


def test_existing_appointment_removes_overlapping_slots(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(tz="UTC", duration=30, start="09:00", end="11:00")
        booking_services.create_appointment(
            service=service, staff=staff,
            start_at=datetime(2026, 7, 6, 9, 0, tzinfo=UTC), enforce_availability=False,
        )
        slots = generate_slots(
            service=service, staff=staff,
            range_start=date(2026, 7, 6), range_end=date(2026, 7, 6),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        starts = {s.start.strftime("%H:%M") for s in slots}
        assert "09:00" not in starts and "09:15" not in starts
        assert "09:30" in starts


def test_time_off_blocks_slots(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(tz="UTC", duration=30, start="09:00", end="11:00")
        TimeOff.objects.create(
            staff=staff,
            start_at=datetime(2026, 7, 6, 9, 0, tzinfo=UTC),
            end_at=datetime(2026, 7, 6, 10, 0, tzinfo=UTC),
        )
        slots = generate_slots(
            service=service, staff=staff,
            range_start=date(2026, 7, 6), range_end=date(2026, 7, 6),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        starts = {s.start.strftime("%H:%M") for s in slots}
        assert not ({"09:00", "09:15", "09:30", "09:45"} & starts)
        assert "10:00" in starts


def test_lead_time_and_max_advance(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(tz="UTC", duration=30, start="09:00", end="17:00")
        now = datetime(2026, 7, 6, 9, 0, tzinfo=UTC)
        slots = generate_slots(
            service=service, staff=staff,
            range_start=date(2026, 7, 6), range_end=date(2026, 7, 13),
            lead_minutes=120, max_advance_days=2, now=now,
        )
        # Nothing before now+2h, nothing after now+2d.
        assert all(s.start >= now + timedelta(minutes=120) for s in slots)
        assert all(s.end <= now + timedelta(days=2) for s in slots)
