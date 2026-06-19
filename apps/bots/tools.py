"""
The bot's ONLY capabilities (B7 strict tool scoping).

Every tool operates in the current tenant schema and goes through the same
authorized booking service as a human. There is no tool that can reach another
tenant or bypass booking correctness. An LLM/function-calling layer (e.g. Claude
tool use) may select among these tools, but it can never invent new ones.
"""
from __future__ import annotations

from datetime import date, datetime

from apps.booking import services as booking_services
from apps.booking.availability import generate_slots
from apps.booking.models import AppointmentStatus, Customer, Service, StaffMember
from apps.business.models import BusinessProfile


def _allowed_services(bot) -> list[Service]:
    qs = Service.objects.filter(is_active=True)
    if bot.exposed_service_ids:
        qs = qs.filter(id__in=bot.exposed_service_ids)
    return list(qs.prefetch_related("staff"))


def list_services(bot) -> list[dict]:
    return [
        {"id": s.id, "name": s.name, "duration_minutes": s.duration_minutes, "price": str(s.price)}
        for s in _allowed_services(bot)
    ]


def check_availability(bot, *, service_id: int, day: date, staff_id: int | None = None) -> list[dict]:
    service = next((s for s in _allowed_services(bot) if s.id == service_id), None)
    if service is None:
        return []
    profile = BusinessProfile.get_solo()
    staff_qs = service.staff.filter(is_active=True)
    if staff_id:
        staff_qs = staff_qs.filter(id=staff_id)
    out = []
    for staff in staff_qs:
        slots = generate_slots(
            service=service, staff=staff, range_start=day, range_end=day,
            lead_minutes=profile.booking_lead_minutes, max_advance_days=profile.max_advance_days,
        )
        out.extend(s.as_dict() for s in slots)
    return out


def create_pending_booking(bot, *, service_id: int, staff_id: int, start_at: datetime,
                           customer_name: str, customer_email: str = "", customer_phone: str = "") -> dict:
    """Create a PENDING appointment for human review. Reuses the same engine, so
    double-booking is impossible even via a bot."""
    service = next((s for s in _allowed_services(bot) if s.id == service_id), None)
    if service is None:
        raise ValueError("Service not available to this bot.")
    staff = StaffMember.objects.filter(id=staff_id, is_active=True).first()
    if staff is None:
        raise ValueError("Unknown staff member.")

    customer = None
    if customer_email:
        customer = Customer.objects.filter(email__iexact=customer_email).first()
    if customer is None:
        customer = Customer.objects.create(
            name=customer_name, email=customer_email, phone=customer_phone
        )

    profile = BusinessProfile.get_solo()
    appt = booking_services.create_appointment(
        service=service, staff=staff, start_at=start_at, customer=customer,
        source="bot", status=AppointmentStatus.PENDING, enforce_availability=True,
        lead_minutes=profile.booking_lead_minutes, max_advance_days=profile.max_advance_days,
    )
    return {"appointment_id": appt.id, "status": appt.status}
