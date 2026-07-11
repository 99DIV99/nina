"""Accounting services + the auto-income hook (B6)."""

import logging

from django.db import IntegrityError, connection
from django.db.models import CharField, F, Value

from apps.accounting.models import Expense, Income, Invoice, Transaction, TransactionType

logger = logging.getLogger("nina.accounting")


def _accounting_enabled() -> bool:
    """True if the CURRENT tenant has the accounting module enabled."""
    tenant = getattr(connection, "tenant", None)
    return bool(tenant and getattr(tenant, "has_accounting", False))


def record_income_for_appointment(appointment) -> Transaction | None:
    """Create one income Transaction for a completed appointment. Idempotent:
    the unique constraint on source_appointment_id prevents double-counting even
    if the signal fires twice (e.g. retried task)."""
    if not _accounting_enabled():
        return None
    try:
        txn, created = Transaction.objects.get_or_create(
            source_appointment_id=appointment.id,
            defaults={
                "type": TransactionType.INCOME,
                "amount": appointment.price,
                "category": "service",
                "description": f"Appointment #{appointment.id}",
                "occurred_on": appointment.start_at.date(),
            },
        )
    except IntegrityError:
        return None
    if created:
        logger.info("auto_income", extra={"target": f"appointment:{appointment.id}"})
    return txn


def add_expense(*, amount, category, description, occurred_on) -> Transaction:
    return Transaction.objects.create(
        type=TransactionType.EXPENSE,
        amount=amount,
        category=category,
        description=description,
        occurred_on=occurred_on,
    )


def period_report(*, date_from, date_to) -> dict:
    from django.db.models import Sum

    qs = Transaction.objects.filter(occurred_on__gte=date_from, occurred_on__lte=date_to)
    income = qs.filter(type=TransactionType.INCOME).aggregate(s=Sum("amount"))["s"] or 0
    expense = qs.filter(type=TransactionType.EXPENSE).aggregate(s=Sum("amount"))["s"] or 0
    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "income": str(income),
        "expense": str(expense),
        "net": str(income - expense),
    }


def get_ledger(*, date_from=None, date_to=None, type_filter="all"):
    """Return a date-descending, unified view of Income and Expense rows."""
    income = Income.objects.all()
    expense = Expense.objects.all()
    if date_from:
        income = income.filter(occurred_on__gte=date_from)
        expense = expense.filter(occurred_on__gte=date_from)
    if date_to:
        income = income.filter(occurred_on__lte=date_to)
        expense = expense.filter(occurred_on__lte=date_to)

    income_rows = income.annotate(
        type=Value("income", output_field=CharField()),
        category_name=F("category__name"),
        vendor=Value("", output_field=CharField()),
    ).values(
        "id", "occurred_on", "amount", "description", "type", "category_name", "payment_method", "vendor"
    )
    expense_rows = expense.annotate(
        type=Value("expense", output_field=CharField()),
        category_name=F("category__name"),
        payment_method=Value("", output_field=CharField()),
    ).values(
        "id", "occurred_on", "amount", "description", "type", "category_name", "payment_method", "vendor"
    )

    if type_filter == "income":
        return income_rows.order_by("-occurred_on", "-id")
    if type_filter == "expense":
        return expense_rows.order_by("-occurred_on", "-id")
    return income_rows.union(expense_rows).order_by("-occurred_on", "-id")


def next_invoice_number() -> str:
    count = Invoice.objects.count() + 1
    return f"INV-{count:05d}"
