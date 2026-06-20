"""
Booking-bot models (B7) -- per tenant. A bot belongs to exactly one tenant
(structurally guaranteed: this table lives in the tenant schema) and acts ONLY
through the same authorized booking service as any other actor. There is no
privileged backdoor.
"""

import secrets

from django.db import models


def _gen_token() -> str:
    return secrets.token_urlsafe(32)


class Bot(models.Model):
    name = models.CharField(max_length=120, default="Booking assistant")
    is_enabled = models.BooleanField(default=True)
    greeting = models.CharField(max_length=500, default="Hi! I can help you book an appointment.")

    # Channels this bot is exposed on (web widget now; whatsapp/telegram later).
    channels = models.JSONField(default=list, blank=True)
    # Whitelist of service ids the bot may book; empty = all active services.
    exposed_service_ids = models.JSONField(default=list, blank=True)
    # Free-form business rules (e.g. {"max_per_day": 20}).
    rules = models.JSONField(default=dict, blank=True)

    # Secret used to authenticate inbound webhook/widget calls for THIS bot.
    # Scopes the bot to this tenant; never accepted across schemas.
    secret = models.CharField(max_length=64, default=_gen_token, db_index=True)

    # --- Telegram channel ---
    # Bot API token from @BotFather (per tenant; outbound sendMessage uses it).
    telegram_bot_token = models.CharField(max_length=128, blank=True)
    # Secret token we register with setWebhook; Telegram echoes it in the
    # X-Telegram-Bot-Api-Secret-Token header so we can verify inbound updates.
    telegram_webhook_secret = models.CharField(max_length=64, default=_gen_token, db_index=True)

    # --- Bale channel (Telegram-compatible API; secret carried in webhook URL) ---
    bale_bot_token = models.CharField(max_length=128, blank=True)
    bale_webhook_secret = models.CharField(max_length=64, default=_gen_token, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bots_bot"

    def __str__(self) -> str:
        return self.name


class Conversation(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="conversations")
    channel = models.CharField(max_length=20, default="web")
    external_id = models.CharField(max_length=200, blank=True)  # e.g. chat session id
    customer_id = models.BigIntegerField(null=True, blank=True)
    # Working memory for the booking flow (chosen service/staff/time, contact).
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bots_conversation"
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"Conversation #{self.pk} ({self.channel})"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        BOT = "bot", "Bot"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=8, choices=Role.choices)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bots_message"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"
