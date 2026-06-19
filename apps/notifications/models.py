"""Notification log (B5) -- per tenant. Tracks what we sent and delivery state."""
from django.db import models


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Kind(models.TextChoices):
        CONFIRMATION = "confirmation", "Confirmation"
        REMINDER = "reminder", "Reminder"
        RESCHEDULE = "reschedule", "Reschedule"
        CANCELLATION = "cancellation", "Cancellation"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DEAD = "dead", "Dead-lettered"

    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    appointment_id = models.BigIntegerField(null=True, blank=True)
    recipient = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_log"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.kind}/{self.channel} -> {self.recipient} [{self.status}]"
