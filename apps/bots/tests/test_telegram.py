"""B7: per-business Telegram bot — button-based flow, verified webhook, tenant-scoped."""

from datetime import timedelta
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


# ---------------------------------------------------------------------------
# Mocks: capture every outbound Telegram API call instead of hitting the network.
# ---------------------------------------------------------------------------

@pytest.fixture
def captured(monkeypatch):
    """Capture all outbound Telegram calls. Returns a dict of call lists."""
    sends: list[tuple] = []
    button_sends: list[tuple] = []
    acks: list[str] = []
    edits: list[tuple] = []

    monkeypatch.setattr(
        tg, "send_message",
        lambda token, chat_id, text, **kw: sends.append((token, chat_id, text)) or True,
    )
    monkeypatch.setattr(
        tg, "send_message_with_buttons",
        lambda token, chat_id, text, kb=None, **kw: button_sends.append((token, chat_id, text, kb)) or True,
    )
    monkeypatch.setattr(
        tg, "answer_callback_query",
        lambda token, cq_id, text="", **kw: acks.append(cq_id) or True,
    )
    monkeypatch.setattr(
        tg, "edit_message_text",
        lambda *a, **kw: edits.append(a) or True,
    )
    return {"sends": sends, "buttons": button_sends, "acks": acks, "edits": edits}


# ---------------------------------------------------------------------------
# Update helpers — build Telegram-shaped payloads.
# ---------------------------------------------------------------------------

def _msg(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "text": text, "from": {"first_name": "Tg"}}}


def _cb(chat_id, data, cq_id="cb1"):
    return {
        "callback_query": {
            "id": cq_id,
            "data": data,
            "from": {"first_name": "Tg"},
            "message": {"chat": {"id": chat_id}, "message_id": 42},
        }
    }


def _next_monday():
    d = timezone.now().date()
    while d.weekday() != 0 or d <= timezone.now().date():
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Webhook verification (unchanged by the flow refactor)
# ---------------------------------------------------------------------------

def test_unverified_update_rejected(two_tenants, captured):
    alpha, _ = two_tenants
    with tenant_context(alpha):
        Bot.objects.create(name="A", telegram_bot_token="t", is_enabled=True)
    client = APIClient()
    resp = client.post(
        "/api/v1/bots/telegram/webhook",
        _msg("1", "hi"),
        format="json",
        HTTP_HOST="alpha.localhost",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
    )
    assert resp.status_code == 401
    assert captured["sends"] == []
    assert captured["buttons"] == []


def test_telegram_secret_is_tenant_scoped(two_tenants, captured):
    alpha, beta = two_tenants
    with tenant_context(alpha):
        bot = Bot.objects.create(name="A", telegram_bot_token="tok", is_enabled=True)
        secret = bot.telegram_webhook_secret
    client = APIClient()
    resp = client.post(
        "/api/v1/bots/telegram/webhook",
        _msg("9", "hi"),
        format="json",
        HTTP_HOST="beta.localhost",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Button-based flow: full booking WITHOUT OTP
# ---------------------------------------------------------------------------

def test_button_flow_books_without_otp(tenant_factory, captured):
    """When require_phone_otp is False, the flow goes:
    menu → service → date → time → name → phone → confirm → done."""
    biz = tenant_factory(name="TgCo", schema="t_tg", subdomain="tg")
    with tenant_context(biz):
        from apps.business.models import BusinessProfile

        profile = BusinessProfile.get_solo()
        profile.require_phone_otp = False
        profile.save(update_fields=["require_phone_otp"])

        staff, service = build_staff_service(duration=30)
        bot = Bot.objects.create(name="TgBot", telegram_bot_token="TOKEN", is_enabled=True)
        secret = bot.telegram_webhook_secret
        svc_id = service.id

    client = APIClient()

    def webhook(payload):
        return client.post(
            "/api/v1/bots/telegram/webhook",
            payload,
            format="json",
            HTTP_HOST="tg.localhost",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret,
        )

    # 1. Menu — send any text, expect "Book now!" with a button.
    assert webhook(_msg("777", "start")).status_code == 200
    assert any("Book now!" in t for _, _, t, _ in captured["buttons"])

    # 2. Press "Book appointment" → service list.
    assert webhook(_cb("777", "book")).status_code == 200
    assert any("Select a service" in t for _, _, t, _ in captured["buttons"])

    # 3. Pick a service → date picker.
    assert webhook(_cb("777", f"svc:{svc_id}")).status_code == 200
    assert any("Select a date" in t for _, _, t, _ in captured["buttons"])

    # 4. Pick today → time slots.
    assert webhook(_cb("777", "day:0")).status_code == 200

    # 5. Pick the first slot → name prompt.
    assert webhook(_cb("777", "t:0")).status_code == 200
    assert any("Enter your name" in t for _, _, t, _ in captured["buttons"])

    # 6. Enter name → phone prompt.
    assert webhook(_msg("777", "Alice")).status_code == 200
    assert any("Enter your phone number" in t for _, _, t, _ in captured["buttons"])

    # 7. Enter phone → confirm (no OTP since require_phone_otp=False).
    assert webhook(_msg("777", "09123456789")).status_code == 200
    assert any("Please confirm" in t for _, _, t, _ in captured["buttons"])

    # 8. Confirm → done.
    assert webhook(_cb("777", "confirm")).status_code == 200
    assert any("Appointment requested" in t for _, _, t, _ in captured["buttons"])

    with tenant_context(biz):
        conv = Conversation.objects.get(channel="telegram", external_id="777")
        assert conv.state["step"] == "DONE"
        appt = Appointment.objects.get(source="bot")
        assert appt.status == AppointmentStatus.PENDING

    assert all(t == "TOKEN" for t, _, _ in captured["sends"])
    assert all(t == "TOKEN" for t, _, _, _ in captured["buttons"])


# ---------------------------------------------------------------------------
# Button-based flow: cancel resets to menu
# ---------------------------------------------------------------------------

def test_cancel_returns_to_menu(tenant_factory, captured):
    biz = tenant_factory(name="CancelCo", schema="t_cancel", subdomain="cancel")
    with tenant_context(biz):
        build_staff_service(duration=30)
        bot = Bot.objects.create(name="Bot", telegram_bot_token="TOK", is_enabled=True)
        secret = bot.telegram_webhook_secret

    client = APIClient()

    def webhook(payload):
        return client.post(
            "/api/v1/bots/telegram/webhook",
            payload,
            format="json",
            HTTP_HOST="cancel.localhost",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret,
        )

    # Get to menu, then service list.
    webhook(_msg("1", "start"))
    webhook(_cb("1", "book"))

    # Now cancel from SERVICE step → back to MENU.
    assert webhook(_cb("1", "cancel")).status_code == 200
    # The last button message should be "Book now!" (menu).
    last_button_text = captured["buttons"][-1][2]
    assert "Book now!" in last_button_text


# ---------------------------------------------------------------------------
# Callback query parsing
# ---------------------------------------------------------------------------

def test_parse_update_callback_query():
    from apps.bots.telegram import parse_update

    payload = {
        "callback_query": {
            "id": "cq123",
            "data": "svc:5",
            "from": {"first_name": "Bob"},
            "message": {"chat": {"id": 42}, "message_id": 99},
        }
    }
    result = parse_update(payload)
    assert result is not None
    assert result["chat_id"] == "42"
    assert result["callback_data"] == "svc:5"
    assert result["from_name"] == "Bob"
    assert result["message_id"] == 99
    assert result["callback_query_id"] == "cq123"


def test_parse_update_text_message():
    from apps.bots.telegram import parse_update

    payload = {"message": {"chat": {"id": 7}, "text": "hello", "from": {"first_name": "A"}}}
    result = parse_update(payload)
    assert result is not None
    assert result["chat_id"] == "7"
    assert result["text"] == "hello"
    assert "callback_data" not in result


def test_parse_update_ignores_non_text():
    from apps.bots.telegram import parse_update

    # Sticker message — no text → None.
    payload = {"message": {"chat": {"id": 1}, "sticker": {"file_id": "x"}}}
    assert parse_update(payload) is None