"""Your Page (P1 part 2): owner read/write API (/context/page) + the public page
payload (/public/page) that drives the template engine."""

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role
from apps.booking.models import Service, StaffMember
from apps.business.models import BusinessProfile
from conftest import add_member, make_user

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _reset_throttle():
    from django.core.cache import cache

    cache.clear()


def _dash(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_HOST="dash.localhost")
    return client


# --- public payload ---------------------------------------------------------


def test_public_page_payload(tenant):
    with tenant_context(tenant):
        p = BusinessProfile.get_solo()
        p.template = "lumen"
        p.display_name = "Book & Co"
        p.description = "Best in town."
        p.channels = {"telegram": "@bookco", "instagram": "bookco"}
        p.show_services = True
        p.save()
        Service.objects.create(name="Cut", duration_minutes=30, price="20.00", is_active=True)

    resp = APIClient().get("/api/v1/public/page", HTTP_HOST="book.localhost")
    assert resp.status_code == 200
    d = resp.json()
    assert d["template"] == "lumen"
    assert d["title"] == "Book & Co"
    assert d["description"] == "Best in town."
    assert d["channels"]["telegram"] == "@bookco"
    assert d["acceptingBookings"] is True
    assert any(s["name"] == "Cut" for s in d["services"])


def test_booking_blocked_when_offline(tenant):
    with tenant_context(tenant):
        p = BusinessProfile.get_solo()
        p.accepting_bookings = False
        p.require_phone_otp = False
        p.save()
        svc = Service.objects.create(name="Cut", duration_minutes=30, price="20.00", is_active=True)
        staff = StaffMember.objects.create(name="Sam", timezone="UTC", is_active=True)

    resp = APIClient().post(
        "/api/v1/public/book",
        {
            "service": svc.id,
            "staff": staff.id,
            "start_at": "2030-01-01T10:00:00Z",
            "name": "Guest",
        },
        format="json",
        HTTP_HOST="book.localhost",
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "bookings_closed"


# --- owner read / write -----------------------------------------------------


def test_owner_reads_and_updates_page(tenant):
    owner = make_user(email="owner@book.io", phone="09120007001")
    add_member(owner, tenant, role=Role.OWNER)

    read = _dash(owner).get("/api/v1/context/page")
    assert read.status_code == 200
    assert read.json()["template"] == "spotlight"  # default

    upd = _dash(owner).patch(
        "/api/v1/context/page",
        {"template": "storefront", "description": "Hi", "channels": {"website": "x.com"}},
        format="json",
    )
    assert upd.status_code == 200, upd.content
    assert upd.json()["template"] == "storefront"

    with tenant_context(tenant):
        p = BusinessProfile.get_solo()
        assert p.template == "storefront"
        assert p.channels == {"website": "x.com"}


def test_page_patch_rejects_bad_template_and_channel(tenant):
    owner = make_user(email="owner2@book.io", phone="09120007002")
    add_member(owner, tenant, role=Role.OWNER)

    bad_template = _dash(owner).patch(
        "/api/v1/context/page", {"template": "Not A Slug!"}, format="json"
    )
    assert bad_template.status_code == 400

    bad_channel = _dash(owner).patch(
        "/api/v1/context/page", {"channels": {"myspace": "x"}}, format="json"
    )
    assert bad_channel.status_code == 400
