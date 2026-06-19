"""B6 auto-income: completed appointment -> exactly one income transaction."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django_tenants.utils import tenant_context

from apps.accounting.models import Transaction, TransactionType
from apps.booking import services as booking_services
from apps.booking.tests.conftest import build_staff_service

pytestmark = pytest.mark.django_db(transaction=True)
UTC = ZoneInfo("UTC")
WHEN = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)


def test_completion_creates_single_income(tenant_factory):
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
        booking_services.complete(appt)
        income = Transaction.objects.filter(type=TransactionType.INCOME)
        assert income.count() == 1
        assert str(income.first().amount) == "25.00"
        # Idempotent: re-firing the signal does not double-count.
        from apps.accounting.services import record_income_for_appointment

        record_income_for_appointment(appt)
        assert Transaction.objects.filter(type=TransactionType.INCOME).count() == 1


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
        assert Transaction.objects.count() == 0
