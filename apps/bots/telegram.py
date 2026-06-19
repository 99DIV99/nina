"""
Telegram channel adapter (B7).

A concrete adapter on top of the channel-agnostic pipeline. Inbound updates hit
the per-tenant webhook (resolved by host -> schema, like every other request),
are verified by the bot's webhook secret, parsed to text, routed through the SAME
handle_message pipeline, and the reply is sent back via the Telegram Bot API.

Outbound HTTP is isolated here so it can be mocked in tests and swapped for a
queued/Celery sender in production.
"""
from __future__ import annotations

import json
import logging
import urllib.request

logger = logging.getLogger("nina.bots.telegram")

API_BASE = "https://api.telegram.org"


def parse_update(payload: dict) -> dict | None:
    """Extract {chat_id, text, from_name} from a Telegram update, or None if the
    update carries no usable text message."""
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return None
    chat = message.get("chat") or {}
    text = message.get("text")
    if not chat.get("id") or not text:
        return None
    sender = message.get("from") or {}
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or "Guest"
    return {"chat_id": str(chat["id"]), "text": text, "from_name": name}


def send_message(token: str, chat_id: str, text: str, *, timeout: int = 10) -> bool:
    """Send a reply via Telegram. Returns True on success. Network-isolated so
    tests can monkeypatch this single function."""
    url = f"{API_BASE}/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        logger.error("telegram_send_failed", extra={"target": chat_id, "method": str(exc)[:200]})
        return False


def set_webhook(token: str, webhook_url: str, secret: str, *, timeout: int = 10) -> bool:
    """Register the webhook with Telegram (ops helper)."""
    url = f"{API_BASE}/bot{token}/setWebhook"
    data = json.dumps({"url": webhook_url, "secret_token": secret}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        logger.error("telegram_setwebhook_failed", extra={"method": str(exc)[:200]})
        return False
