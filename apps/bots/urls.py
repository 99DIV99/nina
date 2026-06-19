from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bots.views import (
    BotViewSet,
    ReviewQueueView,
    TelegramWebhookView,
    TranscriptView,
    WidgetMessageView,
)

app_name = "bots"

router = DefaultRouter()
router.register("bots", BotViewSet)

urlpatterns = [
    # Public widget entrypoint (bot-secret authenticated).
    path("widget/message", WidgetMessageView.as_view(), name="widget-message"),
    # Telegram webhook (per-tenant; verified by X-Telegram-Bot-Api-Secret-Token).
    path("telegram/webhook", TelegramWebhookView.as_view(), name="telegram-webhook"),
    # Panel: review queue + transcripts.
    path("review-queue", ReviewQueueView.as_view(), name="review-queue"),
    path("review-queue/<int:pk>", ReviewQueueView.as_view(), name="review-decide"),
    path("conversations/<int:pk>/transcript", TranscriptView.as_view(), name="transcript"),
    path("", include(router.urls)),
]
