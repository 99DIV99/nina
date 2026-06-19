"""
Channel abstraction (B5). Notifications are sent through a Channel interface so
SMS (a paid add-on) can be added without touching callers. Email is the default;
SMS is gated by Business.has_sms.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger("nina.notifications")


class Channel(ABC):
    name: str

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str, attachments=None) -> None: ...


class EmailChannel(Channel):
    name = "email"

    def send(self, *, to: str, subject: str, body: str, attachments=None) -> None:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@yourapp.com"),
            to=[to],
        )
        for filename, content, mimetype in attachments or []:
            msg.attach(filename, content, mimetype)
        msg.send(fail_silently=False)


class SMSChannel(Channel):
    """Placeholder for a transactional SMS provider (Twilio/MessageBird)."""

    name = "sms"

    def send(self, *, to: str, subject: str, body: str, attachments=None) -> None:
        # Wire a real provider here. Kept abstract so the add-on is pluggable.
        logger.info("sms_send", extra={"target": to})


def get_channel(name: str) -> Channel:
    return {"email": EmailChannel(), "sms": SMSChannel()}.get(name, EmailChannel())
