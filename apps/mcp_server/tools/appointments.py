"""MCP tools for appointments - calls booking services."""

from datetime import datetime, time as dt_time

from apps.booking.models import Appointment, AppointmentStatus
from apps.booking.services import create_appointment, cancel, reschedule
from apps.mcp_server.registry import register_tool, Tool


def _format_appointment(appointment: Appointment) -> dict:
    """Format appointment for MCP response."""
    return {
        "id": appointment.id,
        "start_at": appointment.start_at.isoformat(),
        "end_at": appointment.end_at.isoformat(),
        "status": appointment.status,
        "customer_id": appointment.customer_id,
        "customer_name": appointment.customer.name if appointment.customer else None,
        "customer_phone": appointment.customer.phone if appointment.customer else None,
        "staff_id": appointment.staff_id,
        "staff_name": appointment.staff.name,
        "service_id": appointment.service_id,
        "service_name": appointment.service.name,
        "price": str(appointment.price) if appointment.price else None,
        "notes": appointment.notes,
    }


def _get_date_filter(params: dict) -> tuple | None:
    """Extract date filter from params."""
    date_str = params.get("date")
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            return (
                datetime.combine(target_date, dt_time.min),
                datetime.combine(target_date, dt_time.max),
            )
        except ValueError:
            return None
    return None


# Tool: list_appointments
register_tool(Tool(
    name="list_appointments",
    description="List appointments with optional filters (date, status, staff)",
    parameters={
        "date": {
            "type": "string",
            "description": "Filter by date (YYYY-MM-DD format)",
        },
        "status": {
            "type": "string",
            "description": "Filter by status (pending, confirmed, completed, cancelled, no_show)",
            "enum": ["pending", "confirmed", "completed", "cancelled", "no_show"],
        },
        "staff_id": {
            "type": "integer",
            "description": "Filter by staff member ID",
        },
    },
    handler=lambda context, params: _list_appointments(context, params),
))


def _list_appointments(context: dict, params: dict) -> dict:
    """Handle list_appointments tool call."""
    queryset = Appointment.objects.select_related(
        "customer", "staff", "service"
    ).order_by("start_at")

    # Apply filters
    date_filter = _get_date_filter(params)
    if date_filter:
        queryset = queryset.filter(start_at__range=date_filter)

    if params.get("status"):
        queryset = queryset.filter(status=params["status"])

    if params.get("staff_id"):
        queryset = queryset.filter(staff_id=params["staff_id"])

    appointments = queryset.all()
    return {
        "appointments": [_format_appt(appt) for appt in appointments],
        "count": len(appointments),
    }


# Tool: get_appointment
register_tool(Tool(
    name="get_appointment",
    description="Get details of a specific appointment",
    parameters={
        "id": {
            "type": "integer",
            "description": "Appointment ID",
        },
    },
    handler=lambda context, params: _get_appointment(context, params),
))


def _get_appointment(context: dict, params: dict) -> dict:
    """Handle get_appointment tool call."""
    try:
        appointment = Appointment.objects.select_related(
            "customer", "staff", "service"
        ).get(id=params["id"])
        return _format_appointment(appointment)
    except Appointment.DoesNotExist:
        raise ValueError(f"Appointment {params['id']} not found")


# Tool: create_appointment (WRITE)
register_tool(Tool(
    name="create_appointment",
    description="Create a new appointment",
    parameters={
        "service_id": {
            "type": "integer",
            "description": "Service ID",
        },
        "staff_id": {
            "type": "integer",
            "description": "Staff member ID",
        },
        "start_at": {
            "type": "string",
            "description": "Start time (ISO 8601 format)",
        },
        "customer_id": {
            "type": "integer",
            "description": "Customer ID (optional)",
        },
        "notes": {
            "type": "string",
            "description": "Notes for the appointment",
        },
    },
    handler=lambda context, params: _create_appointment(context, params),
    write=True,
))


def _create_appointment(context: dict, params: dict) -> dict:
    """Handle create_appointment tool call."""
    from apps.booking.models import Service, StaffMember, Customer

    try:
        service = Service.objects.get(id=params["service_id"])
        staff = StaffMember.objects.get(id=params["staff_id"])
    except (Service.DoesNotExist, StaffMember.DoesNotExist) as e:
        raise ValueError(f"Service or staff not found: {e}")

    customer = None
    if params.get("customer_id"):
        try:
            customer = Customer.objects.get(id=params["customer_id"])
        except Customer.DoesNotExist:
            raise ValueError(f"Customer {params['customer_id']} not found")

    try:
        start_at = datetime.fromisoformat(params["start_at"])
    except ValueError:
        raise ValueError("Invalid start_at format. Use ISO 8601 format.")

    try:
        appointment = create_appointment(
            service=service,
            staff=staff,
            start_at=start_at,
            customer=customer,
            notes=params.get("notes", ""),
            source="mcp",
        )
        return _format_appointment(appointment)
    except Exception as e:
        raise ValueError(f"Failed to create appointment: {e}")


# Tool: cancel_appointment (WRITE)
register_tool(Tool(
    name="cancel_appointment",
    description="Cancel an appointment",
    parameters={
        "id": {
            "type": "integer",
            "description": "Appointment ID to cancel",
        },
    },
    handler=lambda context, params: _cancel_appointment(context, params),
    write=True,
))


def _cancel_appointment(context: dict, params: dict) -> dict:
    """Handle cancel_appointment tool call."""
    try:
        appointment = Appointment.objects.get(id=params["id"])
        cancel(appointment)
        return {"success": True, "id": appointment.id, "status": appointment.status}
    except Appointment.DoesNotExist:
        raise ValueError(f"Appointment {params['id']} not found")
    except Exception as e:
        raise ValueError(f"Failed to cancel appointment: {e}")


# Tool: reschedule_appointment (WRITE)
register_tool(Tool(
    name="reschedule_appointment",
    description="Reschedule an appointment to a new time",
    parameters={
        "id": {
            "type": "integer",
            "description": "Appointment ID to reschedule",
        },
        "new_start_at": {
            "type": "string",
            "description": "New start time (ISO 8601 format)",
        },
    },
    handler=lambda context, params: _reschedule_appointment(context, params),
    write=True,
))


def _reschedule_appointment(context: dict, params: dict) -> dict:
    """Handle reschedule_appointment tool call."""
    try:
        appointment = Appointment.objects.get(id=params["id"])
        new_start = datetime.fromisoformat(params["new_start_at"])
        reschedule(appointment, new_start=new_start)
        return _format_appointment(appointment)
    except Appointment.DoesNotExist:
        raise ValueError(f"Appointment {params['id']} not found")
    except ValueError as e:
        raise ValueError(f"Invalid datetime format: {e}")
    except Exception as e:
        raise ValueError(f"Failed to reschedule appointment: {e}")


# Tool: update_appointment_status (WRITE)
register_tool(Tool(
    name="update_appointment_status",
    description="Update appointment status (confirm, complete, no_show)",
    parameters={
        "id": {
            "type": "integer",
            "description": "Appointment ID",
        },
        "status": {
            "type": "string",
            "description": "New status",
            "enum": ["confirmed", "completed", "no_show"],
        },
    },
    handler=lambda context, params: _update_appointment_status(context, params),
    write=True,
))


def _update_appointment_status(context: dict, params: dict) -> dict:
    """Handle update_appointment_status tool call."""
    try:
        appointment = Appointment.objects.get(id=params["id"])
        new_status = params["status"].upper()

        if new_status == "COMPLETED":
            from apps.booking.services import complete
            complete(appointment)
        elif new_status == "NO_SHOW":
            from apps.booking.services import mark_no_show
            mark_no_show(appointment)
        elif new_status == "CONFIRMED":
            appointment.status = AppointmentStatus.CONFIRMED
            appointment.save(update_fields=["status", "updated_at"])
        else:
            raise ValueError(f"Invalid status: {params['status']}")

        return {"success": True, "id": appointment.id, "status": appointment.status}
    except Appointment.DoesNotExist:
        raise ValueError(f"Appointment {params['id']} not found")
    except Exception as e:
        raise ValueError(f"Failed to update status: {e}")
