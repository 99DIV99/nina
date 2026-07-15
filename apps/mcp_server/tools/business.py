"""MCP tools for business operations."""

from apps.booking.models import Service, StaffMember, BusinessHours
from apps.mcp_server.registry import register_tool, Tool


def _format_service(service: Service) -> dict:
    """Format service for MCP response."""
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price": str(service.price) if service.price else None,
        "is_active": service.is_active,
        "category": service.category.name if service.category else None,
    }


def _format_staff(staff: StaffMember) -> dict:
    """Format staff member for MCP response."""
    return {
        "id": staff.id,
        "name": staff.name,
        "phone": staff.phone,
        "email": staff.email,
        "is_active": staff.is_active,
        "specializations": [s.name for s in staff.services.all()],
    }


# Tool: list_services
register_tool(Tool(
    name="list_services",
    description="List all services with pricing and duration",
    parameters={
        "active_only": {
            "type": "boolean",
            "description": "Only show active services (default true)",
        },
    },
    handler=lambda context, params: _list_services(context, params),
))


def _list_services(context: dict, params: dict) -> dict:
    """Handle list_services tool call."""
    queryset = Service.objects.select_related("category").order_by("name")

    if params.get("active_only", True):
        queryset = queryset.filter(is_active=True)

    services = queryset.all()
    return {
        "services": [_format_service(s) for s in services],
        "count": len(services),
    }


# Tool: get_service
register_tool(Tool(
    name="get_service",
    description="Get details of a specific service",
    parameters={
        "id": {
            "type": "integer",
            "description": "Service ID",
        },
    },
    handler=lambda context, params: _get_service(context, params),
))


def _get_service(context: dict, params: dict) -> dict:
    """Handle get_service tool call."""
    try:
        service = Service.objects.select_related("category").get(id=params["id"])
        return _format_service(service)
    except Service.DoesNotExist:
        raise ValueError(f"Service {params['id']} not found")


# Tool: list_staff
register_tool(Tool(
    name="list_staff",
    description="List all staff members with their specializations",
    parameters={
        "active_only": {
            "type": "boolean",
            "description": "Only show active staff (default true)",
        },
    },
    handler=lambda context, params: _list_staff(context, params),
))


def _list_staff(context: dict, params: dict) -> dict:
    """Handle list_staff tool call."""
    queryset = StaffMember.objects.prefetch_related("services").order_by("name")

    if params.get("active_only", True):
        queryset = queryset.filter(is_active=True)

    staff = queryset.all()
    return {
        "staff": [_format_staff(s) for s in staff],
        "count": len(staff),
    }


# Tool: get_staff
register_tool(Tool(
    name="get_staff",
    description="Get details of a specific staff member",
    parameters={
        "id": {
            "type": "integer",
            "description": "Staff ID",
        },
    },
    handler=lambda context, params: _get_staff(context, params),
))


def _get_staff(context: dict, params: dict) -> dict:
    """Handle get_staff tool call."""
    try:
        staff = StaffMember.objects.prefetch_related("services").get(id=params["id"])
        return _format_staff(staff)
    except StaffMember.DoesNotExist:
        raise ValueError(f"Staff member {params['id']} not found")


# Tool: list_business_hours
register_tool(Tool(
    name="list_business_hours",
    description="List business hours for each day of the week",
    parameters={},
    handler=lambda context, params: _list_business_hours(context, params),
))


def _list_business_hours(context: dict, params: dict) -> dict:
    """Handle list_business_hours tool call."""
    hours = BusinessHours.objects.all().order_by("day_of_week")

    day_names = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }

    return {
        "hours": [
            {
                "day": day_names.get(h.day_of_week, f"Day {h.day_of_week}"),
                "is_closed": h.is_closed,
                "open_time": h.open_time.isoformat() if h.open_time else None,
                "close_time": h.close_time.isoformat() if h.close_time else None,
                "break_start": h.break_start.isoformat() if h.break_start else None,
                "break_end": h.break_end.isoformat() if h.break_end else None,
            }
            for h in hours
        ],
        "count": len(hours),
    }


# Tool: get_business_info
register_tool(Tool(
    name="get_business_info",
    description="Get basic business information (name, contact, etc.)",
    parameters={},
    handler=lambda context, params: _get_business_info(context, params),
))


def _get_business_info(context: dict, params: dict) -> dict:
    """Handle get_business_info tool call."""
    from apps.tenant.models import Domain

    tenant = context.get("tenant")
    if not tenant:
        return {"error": "No tenant in context"}

    domain = Domain.objects.filter(tenant=tenant, is_primary=True).first()

    return {
        "business_name": tenant.business_name or "N/A",
        "subdomain": domain.subdomain if domain else "N/A",
        "timezone": tenant.timezone or "UTC",
        "currency": tenant.currency or "USD",
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }
