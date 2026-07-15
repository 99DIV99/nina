"""MCP tools for accounting."""

from datetime import datetime

from apps.accounting.models import Income, Expense, Invoice
from apps.accounting.services import (
    period_report,
    trend_report,
    staff_report,
    service_report,
    outstanding_invoices,
)
from apps.mcp_server.registry import register_tool, Tool


# Tool: list_income
register_tool(Tool(
    name="list_income",
    description="List income transactions with date range filter",
    parameters={
        "date_from": {
            "type": "string",
            "description": "Start date (YYYY-MM-DD)",
        },
        "date_to": {
            "type": "string",
            "description": "End date (YYYY-MM-DD)",
        },
    },
    handler=lambda context, params: _list_income(context, params),
))


def _list_income(context: dict, params: dict) -> dict:
    """Handle list_income tool call."""
    queryset = Income.objects.select_related("category").order_by("-occurred_on")

    if params.get("date_from"):
        try:
            date_from = datetime.strptime(params["date_from"], "%Y-%m-%d").date()
            queryset = queryset.filter(occurred_on__gte=date_from)
        except ValueError:
            pass

    if params.get("date_to"):
        try:
            date_to = datetime.strptime(params["date_to"], "%Y-%m-%d").date()
            queryset = queryset.filter(occurred_on__lte=date_to)
        except ValueError:
            pass

    income_list = queryset.all()[:50]  # Limit to 50

    return {
        "income": [
            {
                "id": inc.id,
                "amount": str(inc.amount),
                "occurred_on": str(inc.occurred_on),
                "description": inc.description,
                "category": inc.category.name if inc.category else None,
                "payment_method": inc.payment_method,
                "source_appointment_id": inc.source_appointment_id,
            }
            for inc in income_list
        ],
        "count": len(income_list),
    }


# Tool: list_expenses
register_tool(Tool(
    name="list_expenses",
    description="List expense transactions with date range filter",
    parameters={
        "date_from": {
            "type": "string",
            "description": "Start date (YYYY-MM-DD)",
        },
        "date_to": {
            "type": "string",
            "description": "End date (YYYY-MM-DD)",
        },
    },
    handler=lambda context, params: _list_expenses(context, params),
))


def _list_expenses(context: dict, params: dict) -> dict:
    """Handle list_expenses tool call."""
    queryset = Expense.objects.select_related("category").order_by("-occurred_on")

    if params.get("date_from"):
        try:
            date_from = datetime.strptime(params["date_from"], "%Y-%m-%d").date()
            queryset = queryset.filter(occurred_on__gte=date_from)
        except ValueError:
            pass

    if params.get("date_to"):
        try:
            date_to = datetime.strptime(params["date_to"], "%Y-%m-%d").date()
            queryset = queryset.filter(occurred_on__lte=date_to)
        except ValueError:
            pass

    expense_list = queryset.all()[:50]  # Limit to 50

    return {
        "expenses": [
            {
                "id": exp.id,
                "amount": str(exp.amount),
                "occurred_on": str(exp.occurred_on),
                "description": exp.description,
                "category": exp.category.name if exp.category else None,
                "vendor": exp.vendor,
                "is_recurring": exp.is_recurring,
            }
            for exp in expense_list
        ],
        "count": len(expense_list),
    }


# Tool: get_financial_summary
register_tool(Tool(
    name="get_financial_summary",
    description="Get profit and loss summary for a date range",
    parameters={
        "date_from": {
            "type": "string",
            "description": "Start date (YYYY-MM-DD)",
        },
        "date_to": {
            "type": "string",
            "description": "End date (YYYY-MM-DD)",
        },
    },
    handler=lambda context, params: _get_financial_summary(context, params),
))


def _get_financial_summary(context: dict, params: dict) -> dict:
    """Handle get_financial_summary tool call."""
    try:
        date_from = datetime.strptime(params["date_from"], "%Y-%m-%d").date()
        date_to = datetime.strptime(params["date_to"], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")

    return period_report(date_from=date_from, date_to=date_to)


# Tool: list_invoices
register_tool(Tool(
    name="list_invoices",
    description="List invoices with outstanding amounts",
    parameters={
        "date_from": {
            "type": "string",
            "description": "Filter from this date (YYYY-MM-DD, optional)",
        },
        "date_to": {
            "type": "string",
            "description": "Filter until this date (YYYY-MM-DD, optional)",
        },
    },
    handler=lambda context, params: _list_invoices(context, params),
))


def _list_invoices(context: dict, params: dict) -> dict:
    """Handle list_invoices tool call."""
    date_from = None
    date_to = None

    if params.get("date_from"):
        try:
            date_from = datetime.strptime(params["date_from"], "%Y-%m-%d").date()
        except ValueError:
            pass

    if params.get("date_to"):
        try:
            date_to = datetime.strptime(params["date_to"], "%Y-%m-%d").date()
        except ValueError:
            pass

    result = outstanding_invoices(date_from=date_from, date_to=date_to)
    return result
