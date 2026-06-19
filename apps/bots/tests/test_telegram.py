"""B7: per-business Telegram bot — verified webhook, tenant-scoped, books via pipeline."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

import apps.bots.telegram as tg
from apps.booking.models import Appointment, AppointmentStatus
from apps.booking.tests.conftest import build_staff_service
from apps.bots.models import Bot, Conversation

pytestmark = pytest.mark.django_db(transaction=True)
UTC = ZoneInfo("UTC")


@pytest.fixture
def captured_sends(monkeypatch):
    sent = []
    monkeypatch.setattr(tg, "send_message", lambda token, chat_id, text, **kw: sent.append((token, chat_id, text)) or True)
    return sent


def _update(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "text": text, "from": {"first_name": "Tg"}}}


def _next_monday():
    d = timezone.now().date()
    while d.weekday() != 0 or d <= timezone.now().date():
        d += timedelta(days=1)
    return d


def test_unverified_update_rejected(two_tenants, captured_sends):
    alpha, _ = two_tenants
    with tenant_context(alpha):
        Bot.objects.create(name="A", telegram_bot_token="t", is_enabled=True)
    client = APIClient()
    resp = client.post("/api/v1/bots/telegram/webhook", _update("1", "hi"),
                       format="json", HTTP_HOST="alpha.localhost",
                       HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong")
    assert resp.status_code == 401
    assert captured_sends == []


def test_telegram_secret_is_tenant_scoped(two_tenants, captured_sends):
    alpha, beta = two_tenants
    with tenant_context(alpha):
        bot = Bot.objects.create(name="A", telegram_bot_token="tok", is_enabled=True)
        secret = bot.telegram_webhook_secret
    client = APIClient()
    # alpha's secret against beta's host -> not found in beta schema -> 401.
    resp = client.post("/api/v1/bots/telegram/webhook", _update("9", "hi"),
                       format="json", HTTP_HOST="beta.localhost",
                       HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)
    assert resp.status_code == 401


def test_full_booking_over_telegram(tenant_factory, captured_sends):
    biz = tenant_factory(name="TgCo", schema="t_tg", subdomain="tg")
    day = _next_monday()
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        bot = Bot.objects.create(name="TgBot", telegram_bot_token="TOKEN", is_enabled=True)
        secret = bot.telegram_webhook_secret
        svc_id = service.id

    client = APIClient()

    def send(text):
        return client.post("/api/v1/bots/telegram/webhook", _update("777", text),
                           format="json", HTTP_HOST="tg.localhost",
                           HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)

    for msg in ["hello", "services", f"service #{svc_id}", f"{day.isoformat()} 10:00", "guest@tg.io", "book"]:
        assert send(msg).status_code == 200

    # One conversation on the telegram channel, and a pending bot appointment.
    with tenant_context(biz):
        conv = Conversation.objects.get(channel="telegram", external_id="777")
        assert conv.bot_id == bot.id
        appt = Appointment.objects.get(source="bot")
        assert appt.status == AppointmentStatus.PENDING
    # Replies were sent back through Telegram with the tenant's token.
    assert captured_sends and all(t == "TOKEN" for t, _, _ in captured_sends)
