"""MCP tools for customers."""

from apps.booking.models import Customer
from apps.mcp_server.registry import register_tool, Tool


def _format_customer(customer: Customer) -> dict:
    """Format customer for MCP response."""
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "notes": customer.notes,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
    }


# Tool: list_customers
register_tool(Tool(
    name="list_customers",
    description="List customers with optional search",
    parameters={
        "query": {
            "type": "string",
            "description": "Search in name or phone",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum results (default 50)",
        },
    },
    handler=lambda context, params: _list_customers(context, params),
))


def _list_customers(context: dict, params: dict) -> dict:
    """Handle list_customers tool call."""
    queryset = Customer.objects.all()

    if params.get("query"):
        query = params["query"]
        queryset = queryset.filter(name__icontains=query) | queryset.filter(
            phone__icontains=query
        )

    limit = min(params.get("limit", 50), 100)
    customers = queryset.all()[:limit]

    return {
        "customers": [_format_customer(c) for c in customers],
        "count": len(customers),
    }


# Tool: get_customer
register_tool(Tool(
    name="get_customer",
    description="Get a customer with their visit history",
    parameters={
        "id": {
            "type": "integer",
            "description": "Customer ID",
        },
    },
    handler=lambda context, params: _get_customer(context, params),
))


def _get_customer(context: dict, params: dict) -> dict:
    """Handle get_customer tool call."""
    try:
        customer = Customer.objects.get(id=params["id"])
    except Customer.DoesNotExist:
        raise ValueError(f"Customer {params['id']} not found")

    # Get recent appointments
    from apps.booking.models import Appointment
    recent_appts = Appointment.objects.filter(
        customer=customer
    ).select_related("service", "staff").order_by("-start_at")[:5]

    return {
        "customer": _format_customer(customer),
        "recent_appointments": [
            {
                "id": apt.id,
                "date": apt.start_at.isoformat(),
                "service": apt.service.name,
                "staff": apt.staff.name,
                "status": apt.status,
            }
            for apt in recent_appts
        ],
    }


# Tool: create_customer (WRITE)
register_tool(Tool(
    name="create_customer",
    description="Create a new customer",
    parameters={
        "name": {
            "type": "string",
            "description": "Customer name",
        },
        "phone": {
            "type": "string",
            "description": "Phone number",
        },
        "email": {
            "type": "string",
            "description": "Email address (optional)",
        },
        "notes": {
            "type": "string",
            "description": "Notes (optional)",
        },
    },
    handler=lambda context, params: _create_customer(context, params),
    write=True,
))


def _create_customer(context: dict, params: dict) -> dict:
    """Handle create_customer tool call."""
    if not params.get("name"):
        raise ValueError("Customer name is required")

    if not params.get("phone"):
        raise ValueError("Customer phone is required")

    # Check if customer with same phone exists
    existing = Customer.objects.filter(phone=params["phone"]).first()
    if existing:
        return _format_customer(existing)

    customer = Customer.objects.create(
        name=params["name"],
        phone=params["phone"],
        email=params.get("email", ""),
        notes=params.get("notes", ""),
    )

    return _format_customer(customer)
