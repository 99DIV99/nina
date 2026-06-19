"""
PERMANENT GATE: timezone + DST correctness (B4).

Availability is computed in the staff's local timezone and emitted in UTC. The
same local wall-clock hour maps to DIFFERENT UTC instants either side of a DST
transition -- the engine must get this right.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django_tenants.utils import tenant_context

from apps.booking.availability import generate_slots

from .conftest import build_staff_service

pytestmark = pytest.mark.django_db(transaction=True)

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _first_slot_on(slots, day, tz):
    for s in slots:
        if s.start.astimezone(tz).date() == day:
            return s
    return None


def test_local_hours_map_to_correct_utc(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(
            tz="America/New_York", duration=30, start="09:00", end="17:00"
        )
        # A plain summer Monday (EDT, UTC-4): 09:00 local == 13:00 UTC.
        slots = generate_slots(
            service=service,
            staff=staff,
            range_start=date(2026, 7, 6),
            range_end=date(2026, 7, 6),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        first = _first_slot_on(slots, date(2026, 7, 6), NY)
        assert first is not None
        assert first.start.astimezone(NY).strftime("%H:%M") == "09:00"
        assert first.start.astimezone(UTC).strftime("%H:%M") == "13:00"


def test_dst_boundary_shifts_utc_offset(tenant):
    """US 'fall back' is 2026-11-01. 09:00 local is UTC-4 (EDT) on 10-30 but
    UTC-5 (EST) on 11-02 -> different UTC hour, proving DST awareness."""
    with tenant_context(tenant):
        staff, service = build_staff_service(
            tz="America/New_York", duration=30, start="09:00", end="17:00"
        )
        before = generate_slots(
            service=service,
            staff=staff,
            range_start=date(2026, 10, 30),
            range_end=date(2026, 10, 30),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        after = generate_slots(
            service=service,
            staff=staff,
            range_start=date(2026, 11, 2),
            range_end=date(2026, 11, 2),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        b = _first_slot_on(before, date(2026, 10, 30), NY)
        a = _first_slot_on(after, date(2026, 11, 2), NY)
        # Both are 09:00 local...
        assert b.start.astimezone(NY).strftime("%H:%M") == "09:00"
        assert a.start.astimezone(NY).strftime("%H:%M") == "09:00"
        # ...but different UTC hours: 13:00 (EDT) vs 14:00 (EST).
        assert b.start.astimezone(UTC).strftime("%H:%M") == "13:00"
        assert a.start.astimezone(UTC).strftime("%H:%M") == "14:00"
