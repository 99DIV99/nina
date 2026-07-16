"""MCP server views - SSE endpoint and chat API."""

import json
from datetime import datetime

from django.conf import settings
from django.http import (
    HttpResponse,
    StreamingHttpResponse,
    JsonResponse,
    HttpResponseForbidden,
)
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.authorization import current_business, effective_permissions
from apps.accounts.models import Membership
from apps.mcp_server.auth import generate_internal_token, validate_internal_token
from apps.mcp_server.audit import log_auth_failure
from apps.mcp_server.server import MCPSession, mcp_sse_handler
from apps.common.api_schema import ErrorResponseSerializer


class MCPInternalSSEView(APIView):
    """SSE endpoint for MCP protocol (internal Qwen container)."""

    permission_classes = []  # Auth via X-MCP-Token header
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mcp"

    @extend_schema(
        summary="MCP SSE endpoint (internal)",
        description="Server-Sent Events endpoint for MCP protocol. Auth via X-MCP-Token header.",
    )
    def get(self, request):
        """Handle SSE connection."""
        token = request.headers.get("X-MCP-Token")

        if not token:
            log_auth_failure(tenant_id=None, user_id=None, reason="missing_token")
            return HttpResponseForbidden("Missing X-MCP-Token header", status=401)

        # Validate token
        auth_result = validate_internal_token(token)
        if not auth_result:
            log_auth_failure(tenant_id=None, user_id=None, reason="invalid_token")
            return HttpResponseForbidden("Invalid or expired token", status=401)

        tenant_id, user_id, scopes = auth_result

        # Return SSE response
        def event_stream():
            try:
                # For now, send initial connection event
                yield f"event: connected\ndata: {json.dumps({'tenant': tenant_id, 'user': user_id})}\n\n"
                # In a full implementation, we would handle incoming SSE messages
                # from the Qwen container and process MCP protocol messages
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


class MCPHealthView(APIView):
    """Health check for MCP server."""

    permission_classes = []

    @extend_schema(
        summary="MCP server health check",
        responses={200: OpenApiResponse(description="Server is healthy")},
    )
    def get(self, request):
        return JsonResponse({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


class ChatRequestSerializer(serializers.Serializer):
    """Chat request serializer."""
    message = serializers.CharField(max_length=2000)
    stream = serializers.BooleanField(default=False)
    action_id = serializers.CharField(required=False)  # For confirming actions


class ChatResponseSerializer(serializers.Serializer):
    """Chat response serializer."""
    response = serializers.CharField()
    sources = serializers.ListField(child=serializers.CharField(), required=False)
    model = serializers.CharField(required=False)


class ChatView(APIView):
    """Chat endpoint that orchestrates Qwen + MCP."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"

    @extend_schema(
        summary="AI Chat endpoint",
        request=ChatRequestSerializer,
        responses={
            200: ChatResponseSerializer,
            401: OpenApiResponse(ErrorResponseSerializer, "Unauthorized"),
            503: OpenApiResponse(ErrorResponseSerializer, "AI service unavailable"),
        },
    )
    def post(self, request):
        """Handle chat request."""
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        stream = serializer.validated_data.get("stream", False)
        action_id = serializer.validated_data.get("action_id")

        # Get current tenant and user
        business = current_business(request)
        if not business:
            return Response(
                {"error": "No business context"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user

        # Get user's permissions
        permissions = effective_permissions(request)

        # Handle confirmation of pending action
        if action_id:
            return self._handle_confirmation(request, action_id, business, user)

        # Generate internal MCP token (5 minutes)
        from apps.mcp_server.models import MCPInternalToken

        mcp_token = MCPInternalToken.generate(
            tenant=business,  # Note: model uses 'tenant' parameter name
            user=user,
            scopes=list(permissions),  # Convert set to list for JSON serialization
            expires_seconds=300,
        )

        # Build MCP config for Qwen
        from apps.mcp_server.registry import tools_for_permissions

        available_tools = tools_for_permissions(permissions)
        write_tools = [name for name, tool in available_tools.items() if tool.write]

        base_url = getattr(settings, "BASE_URL", "http://localhost:8000")
        mcp_config = {
            "endpoint": f"{base_url}/api/v1/mcp/internal/",
            "token": mcp_token.token,
            "tenant": business.schema_name,
            "tools": list(permissions),  # Tools user has access to
            "write_tools": write_tools,  # NEW: tell Qwen which are write
            "pending_endpoint": f"{base_url}/api/v1/mcp/pending/",  # For creating pending actions
        }

        # Call Qwen container
        try:
            qwen_response = self._call_qwen(
                message=message,
                mcp_config=mcp_config,
                stream=stream,
                write_tools=write_tools,
            )

            # Check if response contains pending actions
            # For now, return as-is - Qwen will need to be updated to return structured actions
            return Response({
                "response": qwen_response.get("text", ""),
                "sources": qwen_response.get("sources", []),
                "model": qwen_response.get("model", "unknown"),
                "requires_action": qwen_response.get("requires_action", False),
                "actions": qwen_response.get("actions", []),
            })

        except Exception as e:
            return Response(
                {"error": f"AI service unavailable: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

    def _handle_confirmation(self, request, action_id: str, business, user):
        """Handle user confirmation of a pending action."""
        from apps.mcp_server.models import PendingAction
        import uuid

        try:
            # Find pending action (for now, simple implementation)
            # In production, store actions in database with TTL
            pending = PendingAction.objects.get(id=action_id, user=user, business=business)
        except PendingAction.DoesNotExist:
            return Response(
                {"error": "Action not found or expired"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Execute the action
        from apps.mcp_server.registry import get_tool

        tool = get_tool(pending.tool_name)
        if not tool:
            return Response(
                {"error": f"Tool {pending.tool_name} not found"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            context = {"tenant": business, "user": user}
            result = tool.handler(context, pending.tool_params)

            # Delete pending action after execution
            pending.delete()

            return Response({
                "response": f"Action completed: {pending.description}",
                "result": result,
            })

        except Exception as e:
            return Response(
                {"error": f"Action failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _call_qwen(self, message: str, mcp_config: dict, stream: bool = False, write_tools: list = None) -> dict:
        """Call Qwen container with MCP config."""
        import httpx

        qwen_endpoint = getattr(settings, "NINA_QWEN_ENDPOINT", "http://qwen:8000")
        qwen_model = getattr(settings, "NINA_QWEN_MODEL", "qwen2.5:1.5b")

        # Build system prompt with write tool instructions
        write_list = write_tools or []
        system_prompt = f"""You are NINA AI, a helpful business assistant.

Available tools: {mcp_config.get("tools", [])}

WRITE TOOLS (require user confirmation before using): {write_list}

IMPORTANT: When you need to use a WRITE tool:
1. DO NOT execute the tool directly
2. Instead, explain what you will do and ask for confirmation
3. Your response should clearly state the action that will be taken

Example: "I'll add customer John (555-1234) to your records. Please confirm."

For READ tools, you can provide answers directly based on the information.
"""

        # Prepare request
        payload = {
            "model": qwen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "mcp": mcp_config,
            "stream": stream,
        }

        # Make request with timeout
        timeout = getattr(settings, "NINA_QWEN_TIMEOUT", 60)

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{qwen_endpoint}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            return response.json()


class ChatToolsView(APIView):
    """Return available MCP tools for current user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Available chat tools",
        responses={
            200: OpenApiResponse(description="List of available tools"),
        },
    )
    def get(self, request):
        """Return tools available to current user."""
        from apps.mcp_server.registry import tools_for_permissions

        business = current_business(request)
        if not business:
            return Response(
                {"error": "No business context"},
                status=status.HTTP_400_BAD_REQUEST
            )

        permissions = effective_permissions(request)

        tools = tools_for_permissions(permissions)

        return Response({
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "is_write": tool.write,
                }
                for tool in tools.values()
            ],
            "write_tools": [name for name, tool in tools.items() if tool.write],
            "count": len(tools),
        })


class CreatePendingActionSerializer(serializers.Serializer):
    """Serializer for creating pending actions."""
    tool_name = serializers.CharField(max_length=100)
    tool_params = serializers.JSONField()
    description = serializers.CharField(max_length=500)


class CreatePendingActionView(APIView):
    """Create a pending action for write tool confirmation (internal only)."""

    permission_classes = []  # Auth via X-MCP-Token header
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mcp"

    @extend_schema(
        summary="Create pending action (internal)",
        request=CreatePendingActionSerializer,
        responses={
            200: OpenApiResponse(description="Pending action created"),
            401: OpenApiResponse(ErrorResponseSerializer, "Unauthorized"),
        },
    )
    def post(self, request):
        """Create a pending action for user confirmation."""
        from apps.mcp_server.models import MCPInternalToken, PendingAction

        # Validate internal token
        token = request.headers.get("X-MCP-Token")
        if not token:
            return Response(
                {"error": "Missing X-MCP-Token header"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        auth_result = validate_internal_token(token)
        if not auth_result:
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        tenant_id, user_id, scopes = auth_result

        serializer = CreatePendingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get business and user
        try:
            from apps.tenant.models import Business
            from apps.accounts.models import User

            business = Business.objects.get(schema_name=tenant_id)
            user = User.objects.get(id=user_id)
        except (Business.DoesNotExist, User.DoesNotExist):
            return Response(
                {"error": "Invalid tenant or user"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create pending action
        action = PendingAction.create(
            tenant=business,
            user=user,
            tool_name=serializer.validated_data["tool_name"],
            tool_params=serializer.validated_data["tool_params"],
            description=serializer.validated_data["description"],
        )

        return Response({
            "action_id": action.id,
            "tool_name": action.tool_name,
            "description": action.description,
            "expires_at": action.expires_at.isoformat(),
        })
