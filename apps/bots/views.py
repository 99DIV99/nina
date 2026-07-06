"""
Bot APIs (B7).
- Public widget endpoint: authenticated by the per-bot secret (tenant-scoped),
  rate-limited, input-sanitized. SECURITY: the secret is matched within the
  CURRENT tenant schema only, so it can never act on another tenant.
- Panel endpoints: configure bots + the human-in-the-loop review queue
  (confirm/reject bot-created bookings), gated by bots.manage.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.authorization import P_BOTS_MANAGE
from apps.accounts.permissions import HasPermission
from apps.booking.models import Appointment, AppointmentStatus
from apps.booking.serializers import AppointmentSerializer
from apps.bots.models import Bot, Conversation, Message
from apps.bots.pipeline import handle_message
from apps.common.api_schema import ErrorResponseSerializer


class BotSerializer(serializers.ModelSerializer):
    telegram_connected = serializers.SerializerMethodField()
    bale_connected = serializers.SerializerMethodField()

    class Meta:
        model = Bot
        fields = (
            "id",
            "name",
            "is_enabled",
            "greeting",
            "channels",
            "exposed_service_ids",
            "rules",
            "telegram_connected",
            "bale_connected",
            "created_at",
        )
        read_only_fields = ("created_at", "telegram_connected", "bale_connected")

    def get_telegram_connected(self, obj) -> bool:
        return bool(obj.telegram_bot_token)

    def get_bale_connected(self, obj) -> bool:
        return bool(obj.bale_bot_token)


class BotViewSet(viewsets.ModelViewSet):
    queryset = Bot.objects.all()
    serializer_class = BotSerializer
    permission_classes = [HasPermission]
    required_permission = P_BOTS_MANAGE

    @extend_schema(
        summary="Rotate the widget secret",
        request=None,
        responses={200: inline_serializer("BotSecret", {"secret": serializers.CharField()})},
    )
    @action(detail=True, methods=["post"], url_path="rotate-secret")
    def rotate_secret(self, request, pk=None):
        from apps.bots.models import _gen_token

        bot = self.get_object()
        bot.secret = _gen_token()
        bot.save(update_fields=["secret"])
        return Response({"secret": bot.secret})

    @extend_schema(
        summary="Connect a Telegram bot (register the webhook)",
        request=inline_serializer(
            "TelegramConnect",
            {
                "telegram_bot_token": serializers.CharField(),
                "register": serializers.BooleanField(required=False, default=True),
            },
        ),
        responses={
            200: inline_serializer(
                "TelegramConnectResponse",
                {
                    "webhook_url": serializers.CharField(),
                    "webhook_secret": serializers.CharField(),
                    "registered_with_telegram": serializers.BooleanField(),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "telegram_bot_token required"),
        },
    )
    @action(detail=True, methods=["post"], url_path="telegram/connect")
    def telegram_connect(self, request, pk=None):
        """Opt-in: a business supplies its own @BotFather token; we register the
        per-tenant webhook with Telegram. Gated by bots.manage (+ has_bots)."""
        import logging
        from apps.bots.telegram import set_webhook

        logger = logging.getLogger("nina.bots.telegram")
        bot = self.get_object()
        token = (request.data.get("telegram_bot_token") or "").strip()
        if not token:
            logger.warning("telegram_connect_no_token", extra={"bot_id": bot.pk})
            return Response(
                {"error": {"code": "token_required", "message": "telegram_bot_token required"}},
                status=400,
            )
        bot.telegram_bot_token = token
        bot.save(update_fields=["telegram_bot_token"])

        # Webhook is host-routed to THIS tenant; Telegram echoes the secret.
        webhook_url = f"https://{request.get_host()}/api/v1/bots/telegram/webhook"
        registered = False
        if request.data.get("register", True):
            registered = set_webhook(token, webhook_url, bot.telegram_webhook_secret)
            logger.info(
                "telegram_connect_attempt",
                extra={
                    "bot_id": bot.pk,
                    "webhook_url": webhook_url,
                    "registered": registered,
                },
            )
        return Response(
            {
                "webhook_url": webhook_url,
                "webhook_secret": bot.telegram_webhook_secret,
                "registered_with_telegram": registered,
            }
        )

    @extend_schema(
        summary="Connect a Bale bot (register the webhook)",
        request=inline_serializer(
            "BaleConnect",
            {
                "bale_bot_token": serializers.CharField(),
                "register": serializers.BooleanField(required=False, default=True),
            },
        ),
        responses={
            200: inline_serializer(
                "BaleConnectResponse",
                {
                    "webhook_url": serializers.CharField(),
                    "webhook_secret": serializers.CharField(),
                    "registered_with_bale": serializers.BooleanField(),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "bale_bot_token required"),
        },
    )
    @action(detail=True, methods=["post"], url_path="bale/connect")
    def bale_connect(self, request, pk=None):
        """Opt-in: a business supplies its Bale bot token; we register the
        per-tenant webhook with Bale. The secret is carried in the webhook URL
        (Bale does not echo a secret header). Gated by bots.manage (+ has_bots)."""
        from apps.bots.bale import set_webhook

        bot = self.get_object()
        token = (request.data.get("bale_bot_token") or "").strip()
        if not token:
            return Response(
                {"error": {"code": "token_required", "message": "bale_bot_token required"}},
                status=400,
            )
        bot.bale_bot_token = token
        bot.save(update_fields=["bale_bot_token"])

        webhook_url = (
            f"https://{request.get_host()}/api/v1/bots/bale/webhook" f"?s={bot.bale_webhook_secret}"
        )
        registered = False
        if request.data.get("register", True):
            registered = set_webhook(token, webhook_url)
        return Response(
            {
                "webhook_url": webhook_url,
                "webhook_secret": bot.bale_webhook_secret,
                "registered_with_bale": registered,
            }
        )


class ReviewQueueView(APIView):
    """Pending, bot-created appointments awaiting human confirm/reject."""

    permission_classes = [HasPermission]
    required_permission = P_BOTS_MANAGE

    @extend_schema(
        summary="List bot-created appointments awaiting review",
        responses={200: AppointmentSerializer(many=True)},
    )
    def get(self, request):
        qs = Appointment.objects.filter(
            source="bot", status=AppointmentStatus.PENDING
        ).select_related("service", "staff", "customer")
        return Response(AppointmentSerializer(qs, many=True).data)

    @extend_schema(
        summary="Confirm or reject a bot-created appointment",
        request=inline_serializer(
            "ReviewDecision",
            {"decision": serializers.ChoiceField(choices=["confirm", "reject"])},
        ),
        responses={
            200: AppointmentSerializer,
            400: OpenApiResponse(ErrorResponseSerializer, "confirm|reject"),
            404: OpenApiResponse(ErrorResponseSerializer, "Not found."),
        },
    )
    def post(self, request, pk):
        appt = Appointment.objects.filter(pk=pk, source="bot").first()
        if appt is None:
            return Response({"error": {"code": "not_found", "message": "Not found."}}, status=404)
        decision = request.data.get("decision")
        from apps.booking import services as booking_services

        if decision == "confirm":
            appt.status = AppointmentStatus.CONFIRMED
            appt.save(update_fields=["status", "updated_at"])
        elif decision == "reject":
            booking_services.cancel(appt)
        else:
            return Response(
                {"error": {"code": "bad_decision", "message": "confirm|reject"}}, status=400
            )
        return Response(AppointmentSerializer(appt).data)


class WidgetMessageView(APIView):
    """Public chat entrypoint. Auth = per-bot secret within this tenant."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "bot"

    @extend_schema(
        summary="Send a message to the booking assistant (web widget)",
        request=inline_serializer(
            "WidgetMessage",
            {
                "text": serializers.CharField(max_length=1000),
                "secret": serializers.CharField(
                    required=False, help_text="Or send as X-Bot-Secret header."
                ),
                "conversation_id": serializers.IntegerField(required=False),
                "session_id": serializers.CharField(required=False),
            },
        ),
        responses={
            200: OpenApiResponse(OpenApiTypes.OBJECT, "Assistant reply + conversation id."),
            401: OpenApiResponse(ErrorResponseSerializer, "Invalid bot credential."),
        },
    )
    def post(self, request):
        secret = request.headers.get("X-Bot-Secret") or request.data.get("secret", "")
        bot = Bot.objects.filter(secret=secret, is_enabled=True).first() if secret else None
        if bot is None:
            return Response(
                {"error": {"code": "bot_auth", "message": "Invalid bot credential."}}, status=401
            )

        text = (request.data.get("text") or "")[:1000].strip()  # input sanitation: cap length
        if not text:
            return Response(
                {"error": {"code": "empty", "message": "Message required."}}, status=400
            )

        conversation_id = request.data.get("conversation_id")
        if conversation_id:
            conversation = Conversation.objects.filter(id=conversation_id, bot=bot).first()
            if conversation is None:
                return Response(
                    {"error": {"code": "no_conversation", "message": "Unknown conversation."}},
                    status=404,
                )
        else:
            conversation = Conversation.objects.create(
                bot=bot, channel="web", external_id=request.data.get("session_id", "")
            )

        result = handle_message(bot, conversation, text)
        return Response(result, status=status.HTTP_200_OK)


class TelegramWebhookView(APIView):
    """
    Inbound Telegram updates for THIS tenant (host-routed). Verified by the
    per-bot webhook secret echoed in X-Telegram-Bot-Api-Secret-Token, matched
    only within the current schema -> a bot can never receive another tenant's
    traffic. Routes callbacks/text through the button-based flow
    (apps.bots.telegram_flow) and replies via the Telegram Bot API.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "bot"

    @extend_schema(
        summary="Telegram webhook (inbound updates for this tenant)",
        request=OpenApiTypes.OBJECT,
        responses={200: inline_serializer("WebhookAck", {"ok": serializers.BooleanField()})},
    )
    def post(self, request):
        from apps.bots.telegram import parse_update
        from apps.bots.telegram_flow import handle_update

        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        bot = (
            Bot.objects.filter(telegram_webhook_secret=secret, is_enabled=True).first()
            if secret
            else None
        )
        if bot is None or not bot.telegram_bot_token:
            return Response(
                {"error": {"code": "bot_auth", "message": "Unverified update."}}, status=401
            )

        parsed = parse_update(request.data if isinstance(request.data, dict) else {})
        if parsed is None:
            return Response({"ok": True})  # ack non-text updates so Telegram stops retrying

        conversation, _ = Conversation.objects.get_or_create(
            bot=bot,
            channel="telegram",
            external_id=parsed["chat_id"],
            defaults={"state": {"step": "MENU", "name": parsed["from_name"]}},
        )
        handle_update(bot, conversation, parsed, request.data)
        return Response({"ok": True})


class BaleWebhookView(APIView):
    """
    Inbound Bale updates for THIS tenant (host-routed). Bale does not echo a
    secret header, so the per-bot secret travels in the ?s= query set at
    setWebhook time; matched only within the current schema. Routes text through
    the same pipeline as every other channel and replies via the Bale Bot API.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "bot"

    @extend_schema(
        summary="Bale webhook (inbound updates for this tenant)",
        request=OpenApiTypes.OBJECT,
        responses={200: inline_serializer("BaleWebhookAck", {"ok": serializers.BooleanField()})},
    )
    def post(self, request):
        from apps.bots.bale import parse_update, send_message

        secret = request.query_params.get("s") or request.headers.get("X-Bale-Secret", "")
        bot = (
            Bot.objects.filter(bale_webhook_secret=secret, is_enabled=True).first()
            if secret
            else None
        )
        if bot is None or not bot.bale_bot_token:
            return Response(
                {"error": {"code": "bot_auth", "message": "Unverified update."}}, status=401
            )

        parsed = parse_update(request.data if isinstance(request.data, dict) else {})
        if parsed is None:
            return Response({"ok": True})  # ack non-text updates

        conversation, _ = Conversation.objects.get_or_create(
            bot=bot,
            channel="bale",
            external_id=parsed["chat_id"],
            defaults={"state": {"name": parsed["from_name"]}},
        )
        text = parsed["text"][:1000].strip()
        result = handle_message(bot, conversation, text)
        send_message(bot.bale_bot_token, parsed["chat_id"], result["reply"])
        return Response({"ok": True})


class TranscriptView(APIView):
    permission_classes = [HasPermission]
    required_permission = P_BOTS_MANAGE

    @extend_schema(
        summary="Full message transcript for a conversation",
        responses={
            200: inline_serializer(
                "Transcript",
                {
                    "conversation_id": serializers.IntegerField(),
                    "messages": serializers.ListField(
                        child=inline_serializer(
                            "TranscriptMessage",
                            {
                                "role": serializers.CharField(),
                                "text": serializers.CharField(),
                                "at": serializers.DateTimeField(),
                            },
                        )
                    ),
                },
            ),
            404: OpenApiResponse(ErrorResponseSerializer, "Not found."),
        },
    )
    def get(self, request, pk):
        conversation = Conversation.objects.filter(pk=pk).first()
        if conversation is None:
            return Response({"error": {"code": "not_found", "message": "Not found."}}, status=404)
        messages = Message.objects.filter(conversation=conversation).order_by("created_at")
        return Response(
            {
                "conversation_id": conversation.id,
                "messages": [
                    {"role": m.role, "text": m.text, "at": m.created_at.isoformat()}
                    for m in messages
                ],
            }
        )
