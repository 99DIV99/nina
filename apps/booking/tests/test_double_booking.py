"""
PERMANENT GATE: no double-booking, ever (B4) -- including under concurrency.
"""

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, OperationalError, connection
from django_tenants.utils import schema_context, tenant_context

from apps.booking import services as booking_services
from apps.booking.models import ACTIVE_STATUSES, Appointment
from apps.booking.services import DoubleBooking

from .conftest import build_staff_service

pytestmark = pytest.mark.django_db(transaction=True)

UTC = ZoneInfo("UTC")
WHEN = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)  # a Monday, 10:00 UTC


def test_overlapping_same_staff_rejected(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(duration=30)
        booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, enforce_availability=False
        )
        with pytest.raises(DoubleBooking):
            booking_services.create_appointment(
                service=service,
                staff=staff,
                start_at=WHEN + timedelta(minutes=15),  # overlaps
                enforce_availability=False,
            )


def test_adjacent_same_staff_allowed(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(duration=30)
        booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, enforce_availability=False
        )
        # Starts exactly when the first ends -> no overlap (half-open ranges).
        appt = booking_services.create_appointment(
            service=service,
            staff=staff,
            start_at=WHEN + timedelta(minutes=30),
            enforce_availability=False,
        )
        assert appt.id is not None


def test_same_time_different_staff_allowed(tenant):
    with tenant_context(tenant):
        staff_a, service = build_staff_service(duration=30)
        from apps.booking.models import StaffMember

        staff_b = StaffMember.objects.create(name="Bea", is_active=True)
        service.staff.add(staff_b)
        booking_services.create_appointment(
            service=service, staff=staff_a, start_at=WHEN, enforce_availability=False
        )
        appt = booking_services.create_appointment(
            service=service, staff=staff_b, start_at=WHEN, enforce_availability=False
        )
        assert appt.id is not None


def test_cancelled_appointment_frees_the_slot(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service(duration=30)
        first = booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, enforce_availability=False
        )
        booking_services.cancel(first)
        # Slot is free again -> a new active booking at the same time succeeds.
        appt = booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, enforce_availability=False
        )
        assert appt.status in ACTIVE_STATUSES


def test_concurrent_bookings_only_one_wins(tenant):
    """Two threads race to book the same slot; the DB exclusion constraint must
    let exactly one through."""
    schema = tenant.schema_name
    with tenant_context(tenant):
        staff, service = build_staff_service(duration=30)
        staff_id, service_id = staff.id, service.id

    results = {"ok": 0, "rejected": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def attempt():
        from apps.booking.models import Service, StaffMember

        barrier.wait()  # maximize contention
        try:
            with schema_context(schema):
                svc = Service.objects.get(id=service_id)
                stf = StaffMember.objects.get(id=staff_id)
                booking_services.create_appointment(
                    service=svc, staff=stf, start_at=WHEN, enforce_availability=False
                )
            with lock:
                results["ok"] += 1
        except (DoubleBooking, IntegrityError, OperationalError):
            # IntegrityError = exclusion violation; OperationalError = deadlock
            # victim. Both mean "this booking lost the race" -- never a double-book.
            with lock:
                results["rejected"] += 1
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results["ok"] == 1, results
    assert results["rejected"] == 1, results
    with tenant_context(tenant):
        assert Appointment.objects.filter(status__in=ACTIVE_STATUSES).count() == 1
