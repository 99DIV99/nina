"""Render a NotificationLog into (subject, body, attachments). Per-tenant branded."""
from apps.business.models import BusinessProfile


def render_notification(log):
    from apps.booking.models import Appointment

    profile = BusinessProfile.get_solo()
    brand = profile.display_name or "Your booking"
    appt = Appointment.objects.filter(id=log.appointment_id).select_related("service", "staff").first()

    when = appt.start_at.astimezone() if appt else None
    when_str = when.strftime("%a %d %b %Y, %H:%M %Z") if when else ""
    service = appt.service.name if appt else "your appointment"

    templates = {
        "confirmation": (
            f"{brand}: booking confirmed",
            f"Your booking for {service} is confirmed for {when_str}.",
        ),
        "reminder": (
            f"{brand}: reminder",
            f"Reminder: {service} is coming up on {when_str}.",
        ),
        "reschedule": (
            f"{brand}: booking updated",
            f"Your booking for {service} has been moved to {when_str}.",
        ),
        "cancellation": (
            f"{brand}: booking cancelled",
            f"Your booking for {service} on {when_str} has been cancelled.",
        ),
    }
    subject, body = templates.get(log.kind, (f"{brand}: update", "Your booking was updated."))

    attachments = []
    if appt and log.kind in ("confirmation", "reschedule"):
        from apps.notifications.ics import build_ics

        ics = build_ics(
            uid=f"appt-{appt.id}@nina",
            summary=f"{service} — {brand}",
            start=appt.start_at,
            end=appt.end_at,
            description=f"With {appt.staff.name}",
        )
        attachments.append(("appointment.ics", ics, "text/calendar"))
    return subject, body, attachments
