"""Accounting services + the auto-income hook (B6)."""

import logging
from collections import defaultdict
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import IntegrityError, connection
from django.db.models import CharField, F, Sum, Value
from django.db.models.functions import TruncMonth, TruncWeek

from apps.accounting.models import Expense, Income, Invoice, InvoiceStatus, PaymentStatus as InvoicePaymentStatus

logger = logging.getLogger("nina.accounting")


def _accounting_enabled() -> bool:
    """True if the CURRENT tenant has the accounting module enabled."""
    tenant = getattr(connection, "tenant", None)
    return bool(tenant and getattr(tenant, "has_accounting", False))


def record_income_for_appointment(appointment) -> Income | None:
    """Create an Income only for a completed, fully-paid appointment.

    ``source_appointment_id`` makes the operation idempotent, so the completion
    signal and payment endpoint can both safely attempt to record the income.
    """
    from apps.booking.models import AppointmentStatus, PaymentMethod, PaymentStatus
    from apps.business.models import BusinessProfile

    if not _accounting_enabled():
        return None
    if appointment.status != AppointmentStatus.COMPLETED:
        return None
    if appointment.payment_status != PaymentStatus.PAID:
        return None

    try:
        profile = BusinessProfile.get_solo()
        business_timezone = ZoneInfo(profile.timezone)
    except ZoneInfoNotFoundError:
        business_timezone = ZoneInfo("UTC")

    try:
        income, created = Income.objects.get_or_create(
            source_appointment_id=appointment.id,
            defaults={
                "amount": appointment.payment_amount if appointment.payment_amount is not None else appointment.price,
                "description": f"Appointment #{appointment.id}",
                "occurred_on": appointment.start_at.astimezone(business_timezone).date(),
                "payment_method": appointment.payment_method or PaymentMethod.CASH,
            },
        )
    except IntegrityError:
        return Income.objects.filter(source_appointment_id=appointment.id).first()
    if created:
        logger.info("auto_income", extra={"target": f"appointment:{appointment.id}"})
    if profile.auto_generate_invoices:
        _create_invoice_for_paid_appointment(appointment, income, occurred_on=income.occurred_on)
    return income


def _create_invoice_for_paid_appointment(appointment, income, *, occurred_on):
    """Create the optional paid invoice once; Income remains the source of truth."""
    if Invoice.objects.filter(appointment_id=appointment.id).exists():
        return
    Invoice.objects.create(
        number=next_invoice_number(),
        customer_id=appointment.customer_id,
        appointment_id=appointment.id,
        amount=income.amount,
        status=InvoiceStatus.PAID,
        issued_on=occurred_on,
        payment_status=InvoicePaymentStatus.PAID,
        paid_amount=income.amount,
        paid_on=occurred_on,
    )


def period_report(*, date_from, date_to) -> dict:
    income = _total(Income.objects.filter(occurred_on__range=(date_from, date_to)))
    expense = _total(Expense.objects.filter(occurred_on__range=(date_from, date_to)))
    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "income": str(income),
        "expense": str(expense),
        "net": str(income - expense),
    }


def _total(queryset):
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0")


def _period(date_from, date_to):
    return {"from": str(date_from), "to": str(date_to)}


def trend_report(*, entry_type, interval, date_from, date_to):
    """Aggregate Income or Expense by day, Monday-starting week, or month."""
    model = Income if entry_type == "income" else Expense
    queryset = model.objects.filter(occurred_on__range=(date_from, date_to))
    if interval == "daily":
        bucket = F("occurred_on")
    elif interval == "weekly":
        bucket = TruncWeek("occurred_on")
    elif interval == "monthly":
        bucket = TruncMonth("occurred_on")
    else:
        raise ValueError("Unsupported report interval")

    rows = queryset.annotate(bucket=bucket).values("bucket").annotate(
        total=Sum("amount")
    ).order_by("bucket")
    return {
        "period": _period(date_from, date_to),
        entry_type: [{"date": str(row["bucket"]), "total": str(row["total"])} for row in rows],
    }


def staff_report(*, date_from, date_to):
    """Return booking activity and appointment-derived income grouped by staff."""
    from apps.booking.models import Appointment, StaffMember

    appointments = list(
        Appointment.objects.filter(start_at__date__range=(date_from, date_to)).values(
            "id", "staff_id", "customer_id", "service__name", "status"
        )
    )
    staff_ids = {row["staff_id"] for row in appointments}
    staff_names = dict(StaffMember.objects.filter(id__in=staff_ids).values_list("id", "name"))
    income_by_appointment = dict(
        Income.objects.filter(
            occurred_on__range=(date_from, date_to), source_appointment_id__in=[row["id"] for row in appointments]
        ).values_list("source_appointment_id", "amount")
    )
    rows = {
        staff_id: {
            "id": staff_id,
            "name": staff_names[staff_id],
            "total_customers": set(),
            "total_revenue": Decimal("0"),
            "completed": 0,
            "cancelled": 0,
            "no_show": 0,
            "services": defaultdict(int),
        }
        for staff_id in staff_ids
    }
    for appointment in appointments:
        row = rows[appointment["staff_id"]]
        if appointment["customer_id"] is not None:
            row["total_customers"].add(appointment["customer_id"])
        row["total_revenue"] += income_by_appointment.get(appointment["id"], Decimal("0"))
        if appointment["status"] in ("completed", "cancelled", "no_show"):
            row[appointment["status"]] += 1
        row["services"][appointment["service__name"]] += 1

    staff = []
    for row in rows.values():
        row["total_customers"] = len(row["total_customers"])
        row["total_revenue"] = str(row["total_revenue"])
        row["services"] = dict(sorted(row["services"].items()))
        staff.append(row)
    return {"period": _period(date_from, date_to), "staff": sorted(staff, key=lambda row: row["name"])}


def service_report(*, date_from, date_to):
    """Revenue earned in the period, grouped by the booked service."""
    from apps.booking.models import Appointment

    income = list(Income.objects.filter(
        occurred_on__range=(date_from, date_to), source_appointment_id__isnull=False
    ).values("source_appointment_id", "amount"))
    service_by_appointment = dict(
        Appointment.objects.filter(id__in=[row["source_appointment_id"] for row in income]).values_list(
            "id", "service__name"
        )
    )
    services = defaultdict(lambda: {"appointments": 0, "revenue": Decimal("0")})
    for row in income:
        service_name = service_by_appointment.get(row["source_appointment_id"])
        if service_name:
            services[service_name]["appointments"] += 1
            services[service_name]["revenue"] += row["amount"]
    return {
        "period": _period(date_from, date_to),
        "services": [
            {"name": name, "appointments": values["appointments"], "revenue": str(values["revenue"])}
            for name, values in sorted(services.items())
        ],
    }


def outstanding_invoices(*, date_from, date_to):
    queryset = Invoice.objects.filter(payment_status__in=("unpaid", "partial"))
    if date_from:
        queryset = queryset.filter(issued_on__gte=date_from)
    if date_to:
        queryset = queryset.filter(issued_on__lte=date_to)
    invoices = []
    for invoice in queryset.order_by("due_on", "number"):
        invoices.append({
            "id": invoice.id,
            "number": invoice.number,
            "customer_id": invoice.customer_id,
            "amount": str(invoice.amount),
            "paid_amount": str(invoice.paid_amount),
            "outstanding": str(invoice.amount - invoice.paid_amount),
            "payment_status": invoice.payment_status,
            "issued_on": str(invoice.issued_on or ""),
            "due_on": str(invoice.due_on or ""),
        })
    return {"period": _period(date_from, date_to), "invoices": invoices}


def cash_flow_report(*, date_from, date_to):
    income = Income.objects.filter(occurred_on__range=(date_from, date_to)).values("occurred_on").annotate(
        total=Sum("amount")
    )
    expense = Expense.objects.filter(occurred_on__range=(date_from, date_to)).values("occurred_on").annotate(
        total=Sum("amount")
    )
    days = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0")})
    for row in income:
        days[row["occurred_on"]]["income"] = row["total"]
    for row in expense:
        days[row["occurred_on"]]["expense"] = row["total"]
    return {
        "period": _period(date_from, date_to),
        "cash_flow": [
            {"date": str(day), "income": str(totals["income"]), "expense": str(totals["expense"]),
             "net": str(totals["income"] - totals["expense"])}
            for day, totals in sorted(days.items())
        ],
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
