"""MCP tool registry - register and discover available tools."""

from typing import Callable, Dict, Any

from apps.mcp_server.permissions import get_required_permission


class Tool:
    """Represents an MCP tool."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON schema
        self.handler = handler
        self.required_permission = get_required_permission(name)

    def to_dict(self) -> dict:
        """Convert tool to MCP format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
            },
        }


class Resource:
    """Represents an MCP resource."""

    def __init__(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "application/json",
        handler: Callable = None,
    ):
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type
        self.handler = handler

    def to_dict(self) -> dict:
        """Convert resource to MCP format."""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


# Global registries
_TOOLS: Dict[str, Tool] = {}
_RESOURCES: Dict[str, Resource] = {}


def register_tool(tool: Tool) -> Tool:
    """Register an MCP tool."""
    _TOOLS[tool.name] = tool
    return tool


def register_resource(resource: Resource) -> Resource:
    """Register an MCP resource."""
    _RESOURCES[resource.uri] = resource
    return resource


def get_tool(name: str) -> Tool | None:
    """Get a registered tool by name."""
    return _TOOLS.get(name)


def get_all_tools() -> Dict[str, Tool]:
    """Get all registered tools."""
    return _TOOLS.copy()


def get_all_resources() -> Dict[str, Resource]:
    """Get all registered resources."""
    return _RESOURCES.copy()


def tools_for_permissions(scopes: list) -> Dict[str, Tool]:
    """Filter tools that the user has permission to use."""
    return {
        name: tool
        for name, tool in _TOOLS.items()
        if tool.required_permission is None or tool.required_permission in scopes
    }


def resources_for_permissions(scopes: list) -> Dict[str, Resource]:
    """Filter resources that the user has permission to access."""
    # Resources follow same permissions as tools
    # For now, return all (refine later if needed)
    return _RESOURCES.copy()


# Decorator for easy tool registration
def tool(
    name: str,
    description: str,
    parameters: dict,
):
    """Decorator to register a function as an MCP tool.

    Usage:
        @tool(name="list_appointments", description="...", parameters={...})
        def list_appointments(params):
            ...
    """

    def decorator(func: Callable) -> Callable:
        tool_obj = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=func,
        )
        register_tool(tool_obj)
        return func

    return decorator


def resource(
    uri: str,
    name: str,
    description: str,
    mime_type: str = "application/json",
):
    """Decorator to register a function as an MCP resource.

    Usage:
        @resource(uri="mcp://nina/appointments/today", name="...", description="...")
        def appointments_today():
            ...
    """

    def decorator(func: Callable) -> Callable:
        resource_obj = Resource(
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
            handler=func,
        )
        register_resource(resource_obj)
        return func

    return decorator
