"""
Bale channel adapter (B7).

A dedicated adapter for Bale (https://bale.ai), an Iranian messenger whose Bot API
mirrors Telegram's. Kept as its OWN module (not a parameterised Telegram) so each
channel can evolve independently — Bale's webhook auth differs (no echoed secret
header), so we carry the per-bot secret in the webhook URL query and verify it
here.

Inbound updates -> verified by secret -> parsed to text -> routed through the SAME
handle_message pipeline -> reply sent via the Bale Bot API. Outbound HTTP is
isolated here so it can be mocked in tests.
"""

from __future__ import annotations

import json
import logging
import urllib.request

logger = logging.getLogger("nina.bots.bale")

API_BASE = "https://tapi.bale.ai"


def parse_update(payload: dict) -> dict | None:
    """Extract {chat_id, text, from_name} from a Bale update (Telegram-shaped),
    or None if the update carries no usable text message."""
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
    """Send a reply via Bale. Returns True on success. Network-isolated so tests
    can monkeypatch this single function."""
    url = f"{API_BASE}/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        logger.error("bale_send_failed", extra={"target": chat_id, "method": str(exc)[:200]})
        return False


def set_webhook(token: str, webhook_url: str, *, timeout: int = 10) -> bool:
    """Register the webhook with Bale. The per-bot secret is carried in the
    webhook_url query (Bale does not echo a secret header), so the receiver can
    still verify inbound updates."""
    url = f"{API_BASE}/bot{token}/setWebhook"
    data = json.dumps({"url": webhook_url}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        logger.error("bale_setwebhook_failed", extra={"method": str(exc)[:200]})
        return False
