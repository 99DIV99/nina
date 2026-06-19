"""
Bot APIs (B7).
- Public widget endpoint: authenticated by the per-bot secret (tenant-scoped),
  rate-limited, input-sanitized. SECURITY: the secret is matched within the
  CURRENT tenant schema only, so it can never act on another tenant.
- Panel endpoints: configure bots + the human-in-the-loop review queue
  (confirm/reject bot-created bookings), gated by bots.manage.
"""
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


class BotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bot
        fields = (
            "id", "name", "is_enabled", "greeting", "channels",
            "exposed_service_ids", "rules", "created_at",
        )
        read_only_fields = ("created_at",)


class BotViewSet(viewsets.ModelViewSet):
    queryset = Bot.objects.all()
    serializer_class = BotSerializer
    permission_classes = [HasPermission]
    required_permission = P_BOTS_MANAGE

    @action(detail=True, methods=["post"], url_path="rotate-secret")
    def rotate_secret(self, request, pk=None):
        from apps.bots.models import _gen_token

        bot = self.get_object()
        bot.secret = _gen_token()
        bot.save(update_fields=["secret"])
        return Response({"secret": bot.secret})


class ReviewQueueView(APIView):
    """Pending, bot-created appointments awaiting human confirm/reject."""

    permission_classes = [HasPermission]
    required_permission = P_BOTS_MANAGE

    def get(self, request):
        qs = Appointment.objects.filter(
            source="bot", status=AppointmentStatus.PENDING
        ).select_related("service", "staff", "customer")
        return Response(AppointmentSerializer(qs, many=True).data)

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
            return Response({"error": {"code": "bad_decision", "message": "confirm|reject"}}, status=400)
        return Response(AppointmentSerializer(appt).data)


class WidgetMessageView(APIView):
    """Public chat entrypoint. Auth = per-bot secret within this tenant."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "bot"

    def post(self, request):
        secret = request.headers.get("X-Bot-Secret") or request.data.get("secret", "")
        bot = Bot.objects.filter(secret=secret, is_enabled=True).first() if secret else None
        if bot is None:
            return Response({"error": {"code": "bot_auth", "message": "Invalid bot credential."}}, status=401)

        text = (request.data.get("text") or "")[:1000].strip()  # input sanitation: cap length
        if not text:
            return Response({"error": {"code": "empty", "message": "Message required."}}, status=400)

        conversation_id = request.data.get("conversation_id")
        if conversation_id:
            conversation = Conversation.objects.filter(id=conversation_id, bot=bot).first()
            if conversation is None:
                return Response({"error": {"code": "no_conversation", "message": "Unknown conversation."}}, status=404)
        else:
            conversation = Conversation.objects.create(
                bot=bot, channel="web", external_id=request.data.get("session_id", "")
            )

        result = handle_message(bot, conversation, text)
        return Response(result, status=status.HTTP_200_OK)


class TranscriptView(APIView):
    permission_classes = [HasPermission]
    required_permission = P_BOTS_MANAGE

    def get(self, request, pk):
        conversation = Conversation.objects.filter(pk=pk).first()
        if conversation is None:
            return Response({"error": {"code": "not_found", "message": "Not found."}}, status=404)
        messages = Message.objects.filter(conversation=conversation).order_by("created_at")
        return Response(
            {
                "conversation_id": conversation.id,
                "messages": [
                    {"role": m.role, "text": m.text, "at": m.created_at.isoformat()} for m in messages
                ],
            }
        )
