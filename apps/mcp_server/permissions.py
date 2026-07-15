"""MCP tool to permission mapping."""

from apps.accounts.authorization import (
    P_BOOKING_VIEW,
    P_BOOKING_MANAGE,
    P_CUSTOMER_VIEW,
    P_CUSTOMER_MANAGE,
    P_ACCOUNTING_VIEW,
    P_ACCOUNTING_MANAGE,
    P_STAFF_MANAGE,
    P_SERVICE_MANAGE,
    P_BOTS_MANAGE,
)

# Map each tool to required permission
MCP_TOOL_PERMISSIONS = {
    # Appointments
    "list_appointments": P_BOOKING_VIEW,
    "get_appointment": P_BOOKING_VIEW,
    "create_appointment": P_BOOKING_MANAGE,
    "update_appointment_status": P_BOOKING_MANAGE,
    "reschedule_appointment": P_BOOKING_MANAGE,
    "cancel_appointment": P_BOOKING_MANAGE,

    # Customers
    "list_customers": P_CUSTOMER_VIEW,
    "get_customer": P_CUSTOMER_VIEW,
    "create_customer": P_CUSTOMER_MANAGE,

    # Services
    "list_services": P_BOOKING_VIEW,

    # Staff
    "list_staff": P_BOOKING_VIEW,

    # Accounting
    "list_income": P_ACCOUNTING_VIEW,
    "list_expenses": P_ACCOUNTING_VIEW,
    "get_financial_summary": P_ACCOUNTING_VIEW,
    "list_invoices": P_ACCOUNTING_VIEW,

    # Notifications
    "send_reminder": P_BOTS_MANAGE,
}


def get_required_permission(tool_name: str) -> str | None:
    """Get the required permission for a tool.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        Permission string or None if no permission required
    """
    return MCP_TOOL_PERMISSIONS.get(tool_name)


def check_tool_permission(tool_name: str, scopes: list) -> bool:
    """Check if the given scopes grant permission for a tool.

    Args:
        tool_name: Name of the MCP tool
        scopes: List of permission strings from token

    Returns:
        bool: True if tool can be executed
    """
    required = get_required_permission(tool_name)
    if required is None:
        return True  # No permission required
    return required in scopes
