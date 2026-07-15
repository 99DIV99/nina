"""MCP audit logging functions."""

import time
from typing import Any

from apps.mcp_server.models import MCPRequestAudit


def log_tool_call(
    *,
    token,
    tool_name: str,
    parameters: dict | None = None,
    status: str = "success",
    duration_ms: int | None = None,
    error_message: str | None = None,
    request=None,
):
    """Log an MCP tool call for audit.

    Args:
        token: MCPInternalToken instance
        tool_name: Name of the tool being called
        parameters: Parameters passed to the tool
        status: 'success', 'forbidden', or 'error'
        duration_ms: Execution time in milliseconds
        error_message: Error message if status is not 'success'
        request: Django request (for IP/user agent)
    """
    MCPRequestAudit.objects.create(
        tenant=token.tenant if token else None,
        user=token.user if token else None,
        token=token,
        source="internal",
        tool_name=tool_name,
        resource_uri=None,
        parameters=parameters,
        status=status,
        duration_ms=duration_ms,
        error_message=error_message,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
    )


def log_resource_read(
    *,
    token,
    resource_uri: str,
    status: str = "success",
    duration_ms: int | None = None,
    error_message: str | None = None,
    request=None,
):
    """Log an MCP resource read for audit.

    Args:
        token: MCPInternalToken instance
        resource_uri: URI of the resource being read
        status: 'success', 'forbidden', or 'error'
        duration_ms: Execution time in milliseconds
        error_message: Error message if status is not 'success'
        request: Django request (for IP/user agent)
    """
    MCPRequestAudit.objects.create(
        tenant=token.tenant if token else None,
        user=token.user if token else None,
        token=token,
        source="internal",
        tool_name=None,
        resource_uri=resource_uri,
        parameters=None,
        status=status,
        duration_ms=duration_ms,
        error_message=error_message,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
    )


def log_auth_failure(request=None):
    """Log a failed authentication attempt.

    Args:
        request: Django request (for IP/user agent)
    """
    MCPRequestAudit.objects.create(
        tenant=None,
        user=None,
        token=None,
        source="internal",
        tool_name=None,
        resource_uri=None,
        parameters=None,
        status="forbidden",
        duration_ms=None,
        error_message="Authentication failed",
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
    )


def get_client_ip(request) -> str | None:
    """Extract client IP from request."""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent(request) -> str | None:
    """Extract user agent from request."""
    if not request:
        return None
    return request.META.get("HTTP_USER_AGENT")


class AuditContext:
    """Context manager for timing and logging tool calls."""

    def __init__(self, token, tool_name: str, parameters: dict = None, request=None):
        self.token = token
        self.tool_name = tool_name
        self.parameters = parameters
        self.request = request
        self.start_time = None
        self.result = None
        self.error = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start_time) * 1000) if self.start_time else None

        if exc_type is None:
            log_tool_call(
                token=self.token,
                tool_name=self.tool_name,
                parameters=self.parameters,
                status="success",
                duration_ms=duration_ms,
                request=self.request,
            )
        else:
            error_message = str(exc_val) if exc_val else "Unknown error"
            log_tool_call(
                token=self.token,
                tool_name=self.tool_name,
                parameters=self.parameters,
                status="error",
                duration_ms=duration_ms,
                error_message=error_message,
                request=self.request,
            )
        return False  # Don't suppress exceptions
