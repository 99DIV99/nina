"""
Celery tasks for notifications (B5). Tasks are tenant-aware: they receive the
schema name and run inside that tenant's schema_context, so a worker shared
across tenants never touches the wrong schema.

Retry with backoff; after max retries the log row is dead-lettered.
"""
import logging

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger("nina.notifications")


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification(self, schema_name: str, log_id: int):
    from apps.notifications.channels import get_channel
    from apps.notifications.models import NotificationLog
    from apps.notifications.rendering import render_notification

    with schema_context(schema_name):
        log = NotificationLog.objects.filter(id=log_id).first()
        if log is None or log.status == NotificationLog.Status.SENT:
            return
        log.attempts += 1
        try:
            subject, body, attachments = render_notification(log)
            get_channel(log.channel).send(
                to=log.recipient, subject=subject, body=body, attachments=attachments
            )
        except Exception as exc:  # noqa: BLE001
            log.error = str(exc)[:1000]
            if self.request.retries >= self.max_retries:
                log.status = NotificationLog.Status.DEAD
                log.save(update_fields=["status", "attempts", "error"])
                logger.error("notification_dead", extra={"target": log.recipient})
                return
            log.status = NotificationLog.Status.FAILED
            log.save(update_fields=["status", "attempts", "error"])
            raise self.retry(exc=exc)
        log.status = NotificationLog.Status.SENT
        log.sent_at = timezone.now()
        log.save(update_fields=["status", "attempts", "sent_at"])


@shared_task
def dispatch_reminders_all_tenants(lead_minutes: int = 1440):
    """Celery-beat entrypoint. Fans out reminder dispatch across every active
    tenant schema (each tenant is processed in its own schema_context)."""
    from apps.tenancy.models import Business

    total = 0
    for business in Business.objects.exclude(schema_name="public").filter(is_active=True):
        total += dispatch_due_reminders(business.schema_name, lead_minutes)
    return total


@shared_task
def dispatch_due_reminders(schema_name: str, lead_minutes: int = 1440):
    """Celery-beat entrypoint: enqueue reminders for appointments starting within
    the lead window that have not been reminded yet."""
    from datetime import timedelta

    from apps.booking.models import ACTIVE_STATUSES, Appointment
    from apps.notifications.models import NotificationLog
    from apps.notifications.services import queue_for_appointment

    with schema_context(schema_name):
        now = timezone.now()
        window_end = now + timedelta(minutes=lead_minutes)
        upcoming = Appointment.objects.filter(
            status__in=ACTIVE_STATUSES, start_at__gte=now, start_at__lte=window_end
        )
        count = 0
        for appt in upcoming:
            already = NotificationLog.objects.filter(
                appointment_id=appt.id, kind=NotificationLog.Kind.REMINDER
            ).exists()
            if not already and appt.customer and appt.customer.email:
                queue_for_appointment(appt, kind=NotificationLog.Kind.REMINDER, schema_name=schema_name)
                count += 1
        return count
