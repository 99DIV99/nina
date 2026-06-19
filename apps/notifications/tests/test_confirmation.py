"""B5: booking confirmation queues + sends an email with an .ics attachment."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django_tenants.utils import tenant_context

from apps.booking import services as booking_services
from apps.booking.models import Customer
from apps.booking.tests.conftest import build_staff_service
from apps.notifications.models import NotificationLog

pytestmark = pytest.mark.django_db(transaction=True)
UTC = ZoneInfo("UTC")
WHEN = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)


def test_confirmation_sent_on_booking(tenant_factory):
    biz = tenant_factory(name="NotyCo", schema="t_noty", subdomain="noty")
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        cust = Customer.objects.create(name="Cara", email="cara@test.io")
        mail.outbox.clear()
        booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, customer=cust,
            enforce_availability=False,
        )
        log = NotificationLog.objects.filter(kind="confirmation").first()
        assert log is not None and log.status == "sent"
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == ["cara@test.io"]
        assert any(att[0] == "appointment.ics" for att in msg.attachments)


def test_no_email_without_customer_email(tenant_factory):
    biz = tenant_factory(name="NoMail", schema="t_nomail", subdomain="nomail")
    with tenant_context(biz):
        staff, service = build_staff_service(duration=30)
        cust = Customer.objects.create(name="NoEmail")
        mail.outbox.clear()
        booking_services.create_appointment(
            service=service, staff=staff, start_at=WHEN, customer=cust,
            enforce_availability=False,
        )
        assert NotificationLog.objects.count() == 0
        assert len(mail.outbox) == 0
