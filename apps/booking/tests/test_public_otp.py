"""Public booking is gated by phone OTP when the business requires it."""

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.business.models import BusinessProfile
from apps.otp.services import make_verification_token

from .conftest import build_staff_service

pytestmark = pytest.mark.django_db(transaction=True)

WHEN = "2026-07-06T10:00:00Z"  # a Monday 10:00, inside default hours


def _book(client, sid, stid, **extra):
    body = {
        "service": sid,
        "staff": stid,
        "start_at": WHEN,
        "name": "Guest",
        "phone": "09120000000",
    }
    body.update(extra)
    return client.post("/api/v1/public/book", body, HTTP_HOST="book.localhost", format="json")


def test_booking_blocked_without_verified_phone(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service()  # require_phone_otp defaults True
        sid, stid = service.id, staff.id
    resp = _book(APIClient(), sid, stid)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "phone_unverified"


def test_booking_passes_gate_with_valid_token(tenant):
    with tenant_context(tenant):
        staff, service = build_staff_service()
        sid, stid = service.id, staff.id
    token = make_verification_token("09120000000", "booking")
    resp = _book(APIClient(), sid, stid, otp_token=token)
    # got past the gate (whatever happens next, it's not the phone block)
    assert resp.json().get("error", {}).get("code") != "phone_unverified"


def test_booking_open_when_business_opts_out(tenant):
    with tenant_context(tenant):
        profile = BusinessProfile.get_solo()
        profile.require_phone_otp = False
        profile.save(update_fields=["require_phone_otp"])
        staff, service = build_staff_service()
        sid, stid = service.id, staff.id
    resp = _book(APIClient(), sid, stid)  # no token
    assert resp.json().get("error", {}).get("code") != "phone_unverified"
