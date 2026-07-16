"""MCP server URL configuration."""

from django.urls import path

from apps.mcp_server import views

app_name = "mcp_server"

urlpatterns = [
    # Internal SSE endpoint for Qwen container
    path("internal/", views.MCPInternalSSEView.as_view(), name="internal"),

    # Health check
    path("health/", views.MCPHealthView.as_view(), name="health"),

    # Chat API
    path("chat/", views.ChatView.as_view(), name="chat"),

    # Available tools
    path("tools/", views.ChatToolsView.as_view(), name="tools"),

    # Create pending action (for Qwen write tool interception)
    path("pending/", views.CreatePendingActionView.as_view(), name="pending"),
]
