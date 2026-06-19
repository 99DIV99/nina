"""
Booking service layer (B4). Every appointment mutation goes through here so the
correctness guarantees (atomicity, no double-booking, lifecycle) live in one place
and are reused identically by the panel, the public page, and bots.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.booking import signals
from apps.booking.availability import generate_slots
from apps.booking.models import (
    ACTIVE_STATUSES,
    Appointment,
    AppointmentStatus,
    Customer,
    Service,
    StaffMember,
)
from apps.common.exceptions import DomainError


class SlotUnavailable(DomainError):
    code = "slot_unavailable"
    status_code = 409


class DoubleBooking(DomainError):
    code = "double_booking"
    status_code = 409


def _validate_actors(service: Service, staff: StaffMember) -> None:
    if not service.is_active:
        raise DomainError("Service is not active.", code="service_inactive")
    if not staff.is_active:
        raise DomainError("Staff member is not active.", code="staff_inactive")
    if not service.staff.filter(pk=staff.pk).exists():
        raise DomainError(
            "This staff member does not offer that service.", code="staff_service_mismatch"
        )


def _slot_is_offered(
    service: Service,
    staff: StaffMember,
    start_at: datetime,
    *,
    lead_minutes: int,
    max_advance_days: int | None,
) -> bool:
    day = start_at.astimezone(timezone.get_current_timezone()).date()
    slots = generate_slots(
        service=service,
        staff=staff,
        range_start=day,
        range_end=day,
        lead_minutes=lead_minutes,
        max_advance_days=max_advance_days,
    )
    return any(abs((s.start - start_at).total_seconds()) < 1 for s in slots)


def create_appointment(
    *,
    service: Service,
    staff: StaffMember,
    start_at: datetime,
    customer: Customer | None = None,
    source: str = "panel",
    price=None,
    notes: str = "",
    status: str = AppointmentStatus.PENDING,
    enforce_availability: bool = True,
    lead_minutes: int = 0,
    max_advance_days: int | None = None,
) -> Appointment:
    """Atomically create an appointment. The DB exclusion constraint is the final,
    race-proof guarantee against double-booking. Under high contention Postgres may
    abort one racer as a deadlock victim; we retry it briefly before giving up."""
    if timezone.is_naive(start_at):
        raise DomainError("start_at must be timezone-aware.", code="naive_datetime")

    _validate_actors(service, staff)

    if enforce_availability and not _slot_is_offered(
        service, staff, start_at, lead_minutes=lead_minutes, max_advance_days=max_advance_days
    ):
        raise SlotUnavailable("That time is not available.")

    last_exc: OperationalError | None = None
    for attempt in range(3):
        try:
            return _insert_appointment(
                service=service,
                staff=staff,
                start_at=start_at,
                customer=customer,
                source=source,
                price=price,
                notes=notes,
                status=status,
            )
        except OperationalError as exc:  # deadlock victim -> brief backoff + retry
            if "deadlock" not in str(exc).lower():
                raise
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
    raise DoubleBooking("That slot was just taken.") from last_exc


@transaction.atomic
def _insert_appointment(*, service, staff, start_at, customer, source, price, notes, status):
    end_at = start_at + timedelta(minutes=service.duration_minutes)
    appointment = Appointment(
        service=service,
        staff=staff,
        customer=customer,
        start_at=start_at,
        end_at=end_at,
        status=status,
        price=service.price if price is None else price,
        source=source,
        notes=notes,
    )
    try:
        appointment.save()
    except IntegrityError as exc:
        if "no_double_booking" in str(exc):
            raise DoubleBooking("That slot was just taken.") from exc
        raise
    signals.appointment_created.send(sender=Appointment, appointment=appointment)
    return appointment


@transaction.atomic
def reschedule(
    appointment: Appointment,
    *,
    new_start: datetime,
    enforce_availability: bool = True,
    lead_minutes: int = 0,
    max_advance_days: int | None = None,
) -> Appointment:
    if appointment.status not in ACTIVE_STATUSES:
        raise DomainError("Only active appointments can be rescheduled.", code="not_reschedulable")
    if timezone.is_naive(new_start):
        raise DomainError("new_start must be timezone-aware.", code="naive_datetime")

    if enforce_availability and not _slot_is_offered(
        appointment.service,
        appointment.staff,
        new_start,
        lead_minutes=lead_minutes,
        max_advance_days=max_advance_days,
    ):
        raise SlotUnavailable("That time is not available.")

    old_start = appointment.start_at
    appointment.start_at = new_start
    appointment.end_at = new_start + timedelta(minutes=appointment.service.duration_minutes)
    try:
        appointment.save(update_fields=["start_at", "end_at", "updated_at"])
    except IntegrityError as exc:
        if "no_double_booking" in str(exc):
            raise DoubleBooking("That slot was just taken.") from exc
        raise
    signals.appointment_rescheduled.send(
        sender=Appointment, appointment=appointment, old_start=old_start
    )
    return appointment


@transaction.atomic
def cancel(appointment: Appointment) -> Appointment:
    if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
        raise DomainError("Appointment cannot be cancelled.", code="not_cancellable")
    appointment.status = AppointmentStatus.CANCELLED
    appointment.save(update_fields=["status", "updated_at"])
    signals.appointment_cancelled.send(sender=Appointment, appointment=appointment)
    return appointment


@transaction.atomic
def complete(appointment: Appointment) -> Appointment:
    if appointment.status not in ACTIVE_STATUSES:
        raise DomainError("Only active appointments can be completed.", code="not_completable")
    appointment.status = AppointmentStatus.COMPLETED
    appointment.save(update_fields=["status", "updated_at"])
    # Fires the auto-income hook (B6) when accounting is enabled.
    signals.appointment_completed.send(sender=Appointment, appointment=appointment)
    return appointment


def mark_no_show(appointment: Appointment) -> Appointment:
    if appointment.status not in ACTIVE_STATUSES:
        raise DomainError("Only active appointments can be marked no-show.", code="not_no_show")
    appointment.status = AppointmentStatus.NO_SHOW
    appointment.save(update_fields=["status", "updated_at"])
    return appointment
