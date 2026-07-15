"""MCP server - handles SSE communication for Model Context Protocol."""

import json
import asyncio
from typing import AsyncIterator, Optional
from datetime import datetime

from apps.mcp_server.registry import get_all_tools, tools_for_permissions, get_all_resources, resources_for_permissions
from apps.mcp_server.auth import validate_internal_token
from apps.mcp_server.audit import log_tool_call, log_resource_read, AuditContext
from apps.mcp_server.permissions import check_tool_permission


class MCPError(Exception):
    """MCP protocol error."""
    def __init__(self, code: int, message: str, data: dict = None):
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)


class MCPSession:
    """Manages an MCP session over SSE."""

    BASE_MESSAGE = {"jsonrpc": "2.0"}

    def __init__(self, tenant_id: str, user_id: int, scopes: list):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.scopes = scopes
        self.request_id = 0

    def next_id(self) -> int:
        """Get next request ID."""
        self.request_id += 1
        return self.request_id

    def _make_response(self, result: dict = None, error: dict = None, id: int = None) -> dict:
        """Create a JSON-RPC response."""
        response = self.BASE_MESSAGE.copy()
        if result is not None:
            response["result"] = result
        if error is not None:
            response["error"] = error
        if id is not None:
            response["id"] = id
        return response

    def _make_notification(self, method: str, params: dict = None) -> dict:
        """Create a JSON-RPC notification."""
        notification = self.BASE_MESSAGE.copy()
        notification["method"] = method
        if params:
            notification["params"] = params
        return notification

    async def handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": "nina-mcp-server",
                "version": "1.0.0",
            },
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
        }

    async def handle_tools_list(self) -> dict:
        """Handle tools/list request."""
        tools = tools_for_permissions(self.scopes)
        return {
            "tools": [tool.to_dict() for tool in tools.values()]
        }

    async def handle_tools_call(self, params: dict) -> dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise MCPError(-32602, "Invalid params", {"missing": "name"})

        # Check permission
        if not check_tool_permission(tool_name, self.scopes):
            log_tool_call(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                tool_name=tool_name,
                arguments=arguments,
                denied=True,
            )
            raise MCPError(-32603, "Permission denied", {"tool": tool_name})

        # Get tool
        tools = tools_for_permissions(self.scopes)
        tool = tools.get(tool_name)
        if not tool:
            raise MCPError(-32601, "Tool not found", {"tool": tool_name})

        # Execute with audit
        context = {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "tenant": None,  # Set by middleware if needed
        }

        with AuditContext(self.tenant_id, self.user_id, tool_name):
            try:
                result = tool.handler(context, arguments)
                log_tool_call(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    success=True,
                )
                return {"content": [{"type": "text", "text": json.dumps(result)}]}
            except Exception as e:
                log_tool_call(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    success=False,
                    error=str(e),
                )
                raise MCPError(-32603, str(e), {"tool": tool_name})

    async def handle_resources_list(self) -> dict:
        """Handle resources/list request."""
        resources = resources_for_permissions(self.scopes)
        return {
            "resources": [resource.to_dict() for resource in resources.values()]
        }

    async def handle_resources_read(self, params: dict) -> dict:
        """Handle resources/read request."""
        uri = params.get("uri")
        if not uri:
            raise MCPError(-32602, "Invalid params", {"missing": "uri"})

        resources = resources_for_permissions(self.scopes)
        resource = resources.get(uri)
        if not resource:
            raise MCPError(-32601, "Resource not found", {"uri": uri})

        # Execute handler
        if resource.handler:
            try:
                result = resource.handler()
                log_resource_read(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    resource_uri=uri,
                    success=True,
                )
                return {"contents": [result]}
            except Exception as e:
                log_resource_read(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    resource_uri=uri,
                    success=False,
                    error=str(e),
                )
                raise MCPError(-32603, str(e), {"uri": uri})

        raise MCPError(-32603, "No handler for resource", {"uri": uri})

    async def handle_message(self, message: dict) -> Optional[dict]:
        """Handle an incoming JSON-RPC message."""
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params)
                return self._make_response(result=result, id=msg_id)

            elif method == "tools/list":
                result = await self.handle_tools_list()
                return self._make_response(result=result, id=msg_id)

            elif method == "tools/call":
                result = await self.handle_tools_call(params)
                return self._make_response(result=result, id=msg_id)

            elif method == "resources/list":
                result = await self.handle_resources_list()
                return self._make_response(result=result, id=msg_id)

            elif method == "resources/read":
                result = await self.handle_resources_read(params)
                return self._make_response(result=result, id=msg_id)

            else:
                return self._make_response(
                    error={"code": -32601, "message": "Method not found"},
                    id=msg_id
                )

        except MCPError as e:
            return self._make_response(
                error={"code": e.code, "message": e.message, "data": e.data},
                id=msg_id
            )
        except Exception as e:
            return self._make_response(
                error={"code": -32603, "message": "Internal error", "data": {"detail": str(e)}},
                id=msg_id
            )

    def format_event(self, data: dict) -> str:
        """Format data as SSE event."""
        return f"data: {json.dumps(data)}\n\n"


async def mcp_sse_handler(token: str) -> AsyncIterator[str]:
    """SSE handler for MCP connection.

    Yields SSE-formatted messages.
    """
    # Validate token and get session info
    auth_result = validate_internal_token(token)
    if not auth_result:
        yield f"event: error\ndata: {json.dumps({'code': 401, 'message': 'Invalid or expired token'})}\n\n"
        return

    tenant_id, user_id, scopes = auth_result
    session = MCPSession(tenant_id=tenant_id, user_id=user_id, scopes=scopes)

    # Send initial endpoint event
    yield f"event: endpoint\ndata: {{\"message\": \"MCP server connected\"}}\n\n"

    # In a full implementation, we would keep the connection open
    # and listen for incoming messages. For now, this is a basic handler.
    # The actual Qwen container will open this connection and send messages.


async def process_mcp_request(token: str, message: dict) -> dict:
    """Process a single MCP request (for HTTP POST endpoint).

    This is an alternative to SSE for stateless requests.
    """
    # Validate token
    auth_result = validate_internal_token(token)
    if not auth_result:
        return {
            "jsonrpc": "2.0",
            "error": {"code": 401, "message": "Invalid or expired token"}
        }

    tenant_id, user_id, scopes = auth_result
    session = MCPSession(tenant_id=tenant_id, user_id=user_id, scopes=scopes)

    # Handle the message
    response = await session.handle_message(message)
    return response
