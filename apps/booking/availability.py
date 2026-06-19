"""
Availability / slot-generation engine (B4) -- HIGH-RISK, isolated + exhaustively
tested.

Derives real bookable slots from: recurring business hours - existing active
appointments - time off, honoring service duration, buffers, booking lead time,
and the max-advance window. All timezone math is explicit; slots are produced in
UTC and rendered to the caller's timezone at the edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.booking.models import (
    ACTIVE_STATUSES,
    Appointment,
    BusinessHours,
    Service,
    StaffMember,
    TimeOff,
)

# Granularity of generated start times.
SLOT_STEP = timedelta(minutes=15)


@dataclass(frozen=True)
class Slot:
    start: datetime  # UTC, tz-aware
    end: datetime  # UTC, tz-aware
    staff_id: int

    def as_dict(self, display_tz: ZoneInfo | None = None) -> dict:
        start = self.start.astimezone(display_tz) if display_tz else self.start
        end = self.end.astimezone(display_tz) if display_tz else self.end
        return {"start": start.isoformat(), "end": end.isoformat(), "staff_id": self.staff_id}


@dataclass(frozen=True)
class _Interval:
    start: datetime
    end: datetime


def _staff_tz(staff: StaffMember) -> ZoneInfo:
    try:
        return ZoneInfo(staff.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _working_intervals(staff: StaffMember, day: date_cls, tz: ZoneInfo) -> list[_Interval]:
    """Business hours for `day` as UTC intervals, DST-correct via the local tz."""
    intervals: list[_Interval] = []
    for hours in BusinessHours.objects.filter(staff=staff, weekday=day.weekday()):
        local_start = datetime.combine(day, hours.start_time, tzinfo=tz)
        # Handle windows that end at/after midnight defensively.
        end_day = day if hours.end_time > hours.start_time else day + timedelta(days=1)
        local_end = datetime.combine(end_day, hours.end_time, tzinfo=tz)
        intervals.append(
            _Interval(local_start.astimezone(ZoneInfo("UTC")), local_end.astimezone(ZoneInfo("UTC")))
        )
    return intervals


def _subtract(intervals: list[_Interval], blocks: list[_Interval]) -> list[_Interval]:
    """Remove every block interval from the working intervals."""
    result = list(intervals)
    for block in blocks:
        next_result: list[_Interval] = []
        for itv in result:
            # No overlap -> keep as-is.
            if block.end <= itv.start or block.start >= itv.end:
                next_result.append(itv)
                continue
            # Overlap -> keep the non-overlapping head/tail.
            if block.start > itv.start:
                next_result.append(_Interval(itv.start, block.start))
            if block.end < itv.end:
                next_result.append(_Interval(block.end, itv.end))
        result = next_result
    return result


def _busy_blocks(staff: StaffMember, window_start: datetime, window_end: datetime, service: Service) -> list[_Interval]:
    """Existing appointments (expanded by buffers) + time off, as UTC intervals."""
    blocks: list[_Interval] = []

    appts = Appointment.objects.filter(
        staff=staff,
        status__in=ACTIVE_STATUSES,
        end_at__gt=window_start,
        start_at__lt=window_end,
    )
    before = timedelta(minutes=service.buffer_before_minutes)
    after = timedelta(minutes=service.buffer_after_minutes)
    for appt in appts:
        blocks.append(_Interval(appt.start_at - after, appt.end_at + before))

    for off in TimeOff.objects.filter(
        staff=staff, end_at__gt=window_start, start_at__lt=window_end
    ):
        blocks.append(_Interval(off.start_at, off.end_at))

    return blocks


def generate_slots(
    *,
    service: Service,
    staff: StaffMember,
    range_start: date_cls,
    range_end: date_cls,
    lead_minutes: int = 0,
    max_advance_days: int | None = None,
    now: datetime | None = None,
) -> list[Slot]:
    """All bookable slots for one staff member over [range_start, range_end] (inclusive)."""
    now = now or timezone.now()
    tz = _staff_tz(staff)
    duration = timedelta(minutes=service.duration_minutes)
    earliest = now + timedelta(minutes=lead_minutes)
    latest = None
    if max_advance_days is not None:
        latest = now + timedelta(days=max_advance_days)

    window_start = datetime.combine(range_start, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    window_end = datetime.combine(
        range_end + timedelta(days=1), time.min, tzinfo=tz
    ).astimezone(ZoneInfo("UTC"))

    busy = _busy_blocks(staff, window_start, window_end, service)

    slots: list[Slot] = []
    day = range_start
    while day <= range_end:
        free = _subtract(_working_intervals(staff, day, tz), busy)
        for itv in free:
            cursor = itv.start
            while cursor + duration <= itv.end:
                slot_end = cursor + duration
                if cursor >= earliest and (latest is None or slot_end <= latest):
                    slots.append(Slot(start=cursor, end=slot_end, staff_id=staff.id))
                cursor += SLOT_STEP
        day += timedelta(days=1)

    slots.sort(key=lambda s: s.start)
    return slots


def available_staff_for(service: Service):
    """Staff who can perform the service and are active."""
    qs = service.staff.filter(is_active=True)
    return list(qs)
