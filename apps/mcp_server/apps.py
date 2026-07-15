"""Django app configuration for MCP Server."""

from django.apps import AppConfig


class McpServerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mcp_server"
    label = "mcp_server"
    verbose_name = "MCP Server"

    def ready(self):
        """Initialize MCP server when Django starts."""
        import apps.mcp_server.registry  # noqa: F401
        import apps.mcp_server.signals  # noqa: F401
