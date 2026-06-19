"""Queue notifications + connect booking signals (B5)."""
import logging

from django.conf import settings
from django.db import connection

from apps.notifications.models import NotificationLog

logger = logging.getLogger("nina.notifications")


def queue_for_appointment(appointment, *, kind: str, schema_name: str | None = None) -> NotificationLog | None:
    """Create a queued NotificationLog and dispatch the send task."""
    recipient = appointment.customer.email if appointment.customer else ""
    if not recipient:
        return None

    schema_name = schema_name or getattr(connection, "schema_name", None)
    channel = NotificationLog.Channel.EMAIL
    log = NotificationLog.objects.create(
        channel=channel,
        kind=kind,
        appointment_id=appointment.id,
        recipient=recipient,
        status=NotificationLog.Status.QUEUED,
    )

    from apps.notifications.tasks import send_notification

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        # Eager mode (dev/test): run inline; we are already in the tenant schema.
        send_notification.run(schema_name, log.id)
    else:
        send_notification.delay(schema_name, log.id)
    return log


def connect_signals():
    from django.dispatch import receiver

    from apps.booking.signals import (
        appointment_cancelled,
        appointment_created,
        appointment_rescheduled,
    )

    @receiver(appointment_created, weak=False)
    def _on_created(sender, appointment, **kwargs):
        queue_for_appointment(appointment, kind=NotificationLog.Kind.CONFIRMATION)

    @receiver(appointment_rescheduled, weak=False)
    def _on_rescheduled(sender, appointment, **kwargs):
        queue_for_appointment(appointment, kind=NotificationLog.Kind.RESCHEDULE)

    @receiver(appointment_cancelled, weak=False)
    def _on_cancelled(sender, appointment, **kwargs):
        queue_for_appointment(appointment, kind=NotificationLog.Kind.CANCELLATION)
