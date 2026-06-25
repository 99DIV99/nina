"""
Public, unauthenticated booking API (B4). Guests can browse services, see real
availability, and book without an account. Management of an existing booking is
authorized by a signed token, never by a guessable id.
"""

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.booking import services as booking_services
from apps.booking.models import Appointment, Customer, Service, StaffMember
from apps.booking.serializers import AvailabilityQuerySerializer, ServiceSerializer
from apps.booking.views import _availability_payload
from apps.business.models import DEFAULT_VOCABULARY, BusinessProfile
from apps.common.exceptions import DomainError

_appt_signer = TimestampSigner(salt="nina.public.appointment")


class PublicBusinessView(APIView):
    """Public branding/vocabulary/policies for the booking page (F5).

    Safe, non-PII fields only — enough to render a branded, correctly-worded,
    timezone-aware booking flow without authentication.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        business = request.tenant
        profile = BusinessProfile.get_solo()
        base_vocab = DEFAULT_VOCABULARY.get(business.experience, DEFAULT_VOCABULARY["general"])
        vocabulary = {**base_vocab, **(profile.vocabulary or {})}
        return Response(
            {
                "business": {"name": business.name, "is_active": business.is_active},
                "experience": business.experience,
                "branding": {
                    "displayName": profile.display_name or business.name,
                    "logoUrl": profile.logo_url,
                    "primaryColor": profile.primary_color,
                    "accentColor": profile.accent_color,
                },
                "vocabulary": vocabulary,
                "policies": {
                    "timezone": profile.timezone,
                    "cancellationWindowHours": profile.cancellation_window_hours,
                    "requirePhoneOtp": profile.require_phone_otp,
                },
            }
        )


def manage_token(appointment: Appointment) -> str:
    return _appt_signer.sign(str(appointment.pk))


def _resolve_token(token: str) -> Appointment | None:
    try:
        pk = _appt_signer.unsign(token, max_age=90 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return Appointment.objects.filter(pk=pk).first()


class PublicServiceListView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        services = Service.objects.filter(is_active=True).prefetch_related("staff")
        return Response(ServiceSerializer(services, many=True).data)


class PublicAvailabilityView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        ser = AvailabilityQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        try:
            return Response(_availability_payload(ser.validated_data))
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )


class GuestBookingSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.filter(is_active=True))
    staff = serializers.PrimaryKeyRelatedField(queryset=StaffMember.objects.filter(is_active=True))
    start_at = serializers.DateTimeField()
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    otp_token = serializers.CharField(required=False, allow_blank=True, default="")


class PublicBookingCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        ser = GuestBookingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        profile = BusinessProfile.get_solo()

        # Phone verification gate (secure by default; business can opt out).
        if profile.require_phone_otp:
            from apps.otp.services import check_verification_token

            phone = data.get("phone", "")
            if not phone or not check_verification_token(
                data.get("otp_token", ""), phone, "booking"
            ):
                return Response(
                    {"error": {"code": "phone_unverified", "message": "Verify your phone first."}},
                    status=400,
                )

        customer = None
        if data.get("email"):
            customer = Customer.objects.filter(email__iexact=data["email"]).first()
        if customer is None:
            customer = Customer.objects.create(
                name=data["name"], email=data.get("email", ""), phone=data.get("phone", "")
            )

        try:
            appt = booking_services.create_appointment(
                service=data["service"],
                staff=data["staff"],
                start_at=data["start_at"],
                customer=customer,
                source="public",
                notes=data.get("notes", ""),
                enforce_availability=True,
                lead_minutes=profile.booking_lead_minutes,
                max_advance_days=profile.max_advance_days,
            )
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )

        return Response(
            {
                "id": appt.id,
                "status": appt.status,
                "start_at": appt.start_at.isoformat(),
                "end_at": appt.end_at.isoformat(),
                "manage_token": manage_token(appt),
            },
            status=status.HTTP_201_CREATED,
        )


class PublicBookingManageView(APIView):
    """Guest reschedule/cancel via signed token."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        token = request.data.get("token", "")
        appt = _resolve_token(token)
        if appt is None:
            return Response(
                {"error": {"code": "invalid_token", "message": "Invalid or expired token."}},
                status=404,
            )
        action = request.data.get("action")
        profile = BusinessProfile.get_solo()
        try:
            if action == "cancel":
                appt = booking_services.cancel(appt)
            elif action == "reschedule":
                new_start = serializers.DateTimeField().to_internal_value(
                    request.data.get("start_at")
                )
                appt = booking_services.reschedule(
                    appt,
                    new_start=new_start,
                    enforce_availability=True,
                    lead_minutes=profile.booking_lead_minutes,
                    max_advance_days=profile.max_advance_days,
                )
            else:
                return Response(
                    {"error": {"code": "bad_action", "message": "Unknown action."}}, status=400
                )
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(
            {"id": appt.id, "status": appt.status, "start_at": appt.start_at.isoformat()}
        )
