"""
Telegram channel adapter (B7).

A concrete adapter on top of the channel-agnostic pipeline. Inbound updates hit
the per-tenant webhook (resolved by host -> schema, like every other request),
are verified by the bot's webhook secret, parsed to text/callback, routed through
the button-based flow, and the reply is sent back via the Telegram Bot API.

Outbound HTTP is isolated here so it can be mocked in tests and swapped for a
queued/Celery sender in production.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger("nina.bots.telegram")

API_BASE = "https://api.telegram.org"


def _post(token: str, method: str, payload: dict[str, Any], *, timeout: int = 10) -> dict | None:
    """POST to the Telegram Bot API and return the JSON response, or None on error."""
    url = f"{API_BASE}/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if 200 <= resp.status < 300:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("telegram_%s_failed", method, extra={"error": str(exc)[:200]})
        return None
    return None


def parse_update(payload: dict) -> dict | None:
    """Extract a normalised dict from a Telegram update.

    Handles two update types:
    - ``message`` / ``edited_message``: text from the user → {chat_id, user_id, text, from_name}
    - ``callback_query``: button press → {chat_id, user_id, callback_data, from_name, message_id}

    Returns None for updates that carry neither (stickers, channel posts, etc.).
    """
    # --- Callback query (inline button press) ---
    cq = payload.get("callback_query")
    if cq:
        chat = cq.get("message", {}).get("chat", {})
        sender = cq.get("from") or {}
        name = (
            " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or "Guest"
        )
        return {
            "chat_id": str(chat.get("id", "")),
            "user_id": str(sender.get("id", "")),
            "callback_data": cq.get("data", ""),
            "from_name": name,
            "message_id": cq.get("message", {}).get("message_id"),
            "callback_query_id": cq.get("id", ""),
        }

    # --- Text message ---
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return None
    chat = message.get("chat") or {}
    text = message.get("text")
    if not chat.get("id") or not text:
        return None
    sender = message.get("from") or {}
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or "Guest"
    return {
        "chat_id": str(chat["id"]),
        "user_id": str(sender.get("id", "")),
        "text": text,
        "from_name": name,
    }


# ---------------------------------------------------------------------------
# Outbound: messaging primitives
# ---------------------------------------------------------------------------


def send_message(
    token: str, chat_id: str, text: str, *, timeout: int = 10
) -> bool:
    """Send a plain text reply. Returns True on success."""
    res = _post(token, "sendMessage", {"chat_id": chat_id, "text": text}, timeout=timeout)
    return res is not None


def send_message_with_buttons(
    token: str,
    chat_id: str,
    text: str,
    keyboard: list[list[dict[str, str]]] | None = None,
    *,
    timeout: int = 10,
) -> bool:
    """Send a message with an inline keyboard (buttons).

    ``keyboard`` is a list of rows; each row is a list of button dicts:
    ``{"text": "Label", "callback_data": "payload"}``.
    """
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    res = _post(token, "sendMessage", payload, timeout=timeout)
    return res is not None


def edit_message_text(
    token: str,
    chat_id: str,
    message_id: int,
    text: str,
    keyboard: list[list[dict[str, str]]] | None = None,
    *,
    timeout: int = 10,
) -> bool:
    """Edit an existing message's text (and optionally its keyboard)."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    res = _post(token, "editMessageText", payload, timeout=timeout)
    return res is not None


def answer_callback_query(
    token: str, callback_query_id: str, text: str = "", *, timeout: int = 10
) -> bool:
    """Acknowledge a callback query (removes the loading spinner on the button).

    ``text`` is an optional short toast notification shown to the user.
    """
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    res = _post(token, "answerCallbackQuery", payload, timeout=timeout)
    return res is not None


def set_webhook(token: str, webhook_url: str, secret: str, *, timeout: int = 10) -> bool:
    """Register the webhook with Telegram (ops helper)."""
    url = f"{API_BASE}/bot{token}/setWebhook"
    data = json.dumps({"url": webhook_url, "secret_token": secret}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
            if 200 <= resp.status < 300:
                if not body.get("ok", True):
                    logger.error(
                        "telegram_setwebhook_rejected",
                        extra={
                            "description": body.get("description", "Unknown error"),
                            "error_code": body.get("error_code"),
                            "parameters": body.get("parameters"),
                        },
                    )
                    return False
                logger.info("telegram_setwebhook_success", extra={"url": webhook_url})
                return True
            else:
                logger.error(
                    "telegram_setwebhook_http_error",
                    extra={"status": resp.status, "body": body},
                )
                return False
    except urllib.error.HTTPError as exc:
        # Telegram returned an HTTP error (e.g., 401 for invalid token)
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = str(exc)
        logger.error(
            "telegram_setwebhook_http_error",
            extra={"status": exc.code, "body": body},
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("telegram_setwebhook_exception", extra={"error": str(exc), "type": type(exc).__name__})
        return False