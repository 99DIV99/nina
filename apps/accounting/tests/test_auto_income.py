"""B6 auto-income: a completed and paid appointment creates one Income."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django_tenants.utils import tenant_context

from apps.accounting.models import Income, Invoice
from apps.booking import services as booking_services
from apps.booking.models import PaymentMethod, PaymentStatus
from apps.booking.tests.conftest import build_staff_service
from apps.business.models import BusinessProfile

pytestmark = pytest.mark.django_db(transaction=True)
UTC = ZoneInfo("UTC")
WHEN = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)


def test_completed_and_paid_appointment_creates_single_income(tenant_factory):
    biz = tenant_factory(name="AcctCo", schema="t_acct", subdomain="acct")
    assert biz.has_accounting  # barber default
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        service.price = "25.00"
        service.save()
        appt = booking_services.create_appointment(
            service=service,
            staff=staff,
            start_at=WHEN,
            enforce_availability=False,
            price="25.00",
        )
        appt.payment_status = PaymentStatus.PAID
        appt.payment_method = PaymentMethod.CARD
        appt.payment_amount = "25.00"
        appt.save(update_fields=["payment_status", "payment_method", "payment_amount", "updated_at"])
        booking_services.complete(appt)
        income = Income.objects.all()
        assert income.count() == 1
        assert str(income.first().amount) == "25.00"
        # Idempotent: re-firing the signal does not double-count.
        from apps.accounting.services import record_income_for_appointment

        record_income_for_appointment(appt)
        assert Income.objects.count() == 1


def test_unpaid_completion_does_not_create_income_until_paid(tenant_factory):
    biz = tenant_factory(name="PaidLater", schema="t_paid_later", subdomain="paid-later")
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        appt = booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, enforce_availability=False, price="25.00"
        )
        booking_services.complete(appt)
        assert Income.objects.count() == 0

        appt.payment_status = PaymentStatus.PAID
        appt.payment_method = PaymentMethod.CASH
        appt.payment_amount = "25.00"
        appt.save(update_fields=["payment_status", "payment_method", "payment_amount", "updated_at"])
        from apps.accounting.services import record_income_for_appointment

        record_income_for_appointment(appt)
        assert Income.objects.count() == 1


def test_auto_income_uses_business_local_date(tenant_factory):
    biz = tenant_factory(name="TehranCo", schema="t_tehran", subdomain="tehran")
    with tenant_context(biz):
        profile = BusinessProfile.get_solo()
        profile.timezone = "Asia/Tehran"
        profile.save(update_fields=["timezone", "updated_at"])
        staff, service = build_staff_service(duration=30)
        local_next_day = datetime(2026, 7, 6, 21, 30, tzinfo=UTC)
        appt = booking_services.create_appointment(
            service=service, staff=staff, start_at=local_next_day, enforce_availability=False, price="25.00"
        )
        appt.payment_status = PaymentStatus.PAID
        appt.payment_method = PaymentMethod.CASH
        appt.payment_amount = "25.00"
        appt.save(update_fields=["payment_status", "payment_method", "payment_amount", "updated_at"])
        booking_services.complete(appt)
        assert str(Income.objects.get().occurred_on) == "2026-07-07"


def test_paid_appointment_generates_invoice_when_enabled(tenant_factory):
    biz = tenant_factory(name="InvoiceCo", schema="t_invoice", subdomain="invoice")
    with tenant_context(biz):
        profile = BusinessProfile.get_solo()
        profile.auto_generate_invoices = True
        profile.save(update_fields=["auto_generate_invoices", "updated_at"])
        staff, service = build_staff_service(duration=30)
        appt = booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, enforce_availability=False, price="25.00"
        )
        appt.payment_status = PaymentStatus.PAID
        appt.payment_method = PaymentMethod.ONLINE
        appt.payment_amount = "25.00"
        appt.save(update_fields=["payment_status", "payment_method", "payment_amount", "updated_at"])
        booking_services.complete(appt)
        invoice = Invoice.objects.get(appointment_id=appt.id)
        assert str(invoice.paid_amount) == "25.00"
        assert invoice.payment_status == "paid"


def test_no_income_when_accounting_disabled(tenant_factory):
    biz = tenant_factory(name="GenCo", schema="t_gen", subdomain="gen", business_type="general")
    assert not biz.has_accounting
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        appt = booking_services.create_appointment(
            service=service,
            staff=staff,
            start_at=WHEN,
            enforce_availability=False,
        )
        booking_services.complete(appt)
        assert Income.objects.count() == 0
