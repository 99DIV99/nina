"""B7: bot books a PENDING appointment into the panel; bot secret is tenant-scoped."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.booking.models import Appointment, AppointmentStatus
from apps.booking.tests.conftest import build_staff_service
from apps.bots.models import Bot, Conversation
from apps.bots.pipeline import handle_message

pytestmark = pytest.mark.django_db(transaction=True)
UTC = ZoneInfo("UTC")


def _next_monday_10():
    d = timezone.now().date()
    while d.weekday() != 0 or d <= timezone.now().date():
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=UTC), d


def test_bot_creates_pending_appointment(tenant_factory):
    biz = tenant_factory(name="BotCo", schema="t_bot", subdomain="bot")
    when, day = _next_monday_10()
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        bot = Bot.objects.create(name="Asst")
        conv = Conversation.objects.create(bot=bot)
        handle_message(bot, conv, "hello")
        handle_message(bot, conv, "services")
        handle_message(bot, conv, f"service #{service.id}")
        handle_message(bot, conv, f"{day.isoformat()} 10:00")
        handle_message(bot, conv, "me@guest.io")
        result = handle_message(bot, conv, "book")
        assert "requested" in result["reply"].lower()
        appt = Appointment.objects.get(source="bot")
        assert appt.status == AppointmentStatus.PENDING  # lands in review queue
        assert appt.staff_id == staff.id


def test_bot_secret_is_tenant_scoped(two_tenants):
    """A bot secret minted in alpha must NOT authenticate against beta."""
    alpha, beta = two_tenants
    with tenant_context(alpha):
        bot = Bot.objects.create(name="AlphaBot")
        secret = bot.secret

    client = APIClient()
    # Same secret, pointed at beta -> no such bot in beta's schema -> 401.
    resp = client.post(
        "/api/v1/bots/widget/message",
        {"secret": secret, "text": "hi"},
        format="json",
        HTTP_HOST="beta.localhost",
    )
    assert resp.status_code == 401

    # Works against alpha.
    ok = client.post(
        "/api/v1/bots/widget/message",
        {"secret": secret, "text": "hi"},
        format="json",
        HTTP_HOST="alpha.localhost",
    )
    assert ok.status_code == 200
