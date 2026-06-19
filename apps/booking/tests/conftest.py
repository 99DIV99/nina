import pytest
from django_tenants.utils import tenant_context

from apps.booking.models import BusinessHours, Service, StaffMember


@pytest.fixture
def tenant(tenant_factory):
    return tenant_factory(name="BookCo", schema="t_book", subdomain="book")


def build_staff_service(*, tz="UTC", duration=30, buffer_before=0, buffer_after=0,
                        weekdays=range(0, 7), start="09:00", end="17:00"):
    staff = StaffMember.objects.create(name="Sam", timezone=tz, is_active=True)
    service = Service.objects.create(
        name="Cut", duration_minutes=duration,
        buffer_before_minutes=buffer_before, buffer_after_minutes=buffer_after,
        price="20.00", is_active=True,
    )
    service.staff.add(staff)
    for wd in weekdays:
        BusinessHours.objects.create(staff=staff, weekday=wd, start_time=start, end_time=end)
    return staff, service


__all__ = ["tenant", "build_staff_service", "tenant_context"]
