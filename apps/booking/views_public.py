"""
Public, unauthenticated booking API (B4). Guests can browse services, see real
availability, and book without an account. Management of an existing booking is
authorized by a signed token, never by a guessable id.
"""

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Max, Min
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.booking import services as booking_services
from apps.booking.models import Appointment, BusinessHours, Customer, Service, StaffMember
from apps.booking.serializers import AvailabilityQuerySerializer, ServiceSerializer
from apps.booking.views import AvailabilityResponseSerializer, _availability_payload
from apps.business.models import DEFAULT_VOCABULARY, BusinessProfile
from apps.common.api_schema import ErrorResponseSerializer
from apps.common.exceptions import DomainError

_appt_signer = TimestampSigner(salt="nina.public.appointment")


class PublicBusinessView(APIView):
    """Public branding/vocabulary/policies for the booking page (F5).

    Safe, non-PII fields only — enough to render a branded, correctly-worded,
    timezone-aware booking flow without authentication.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        summary="Public branding, vocabulary and policies for the booking page",
        responses={
            200: inline_serializer(
                "PublicBusiness",
                {
                    "business": inline_serializer(
                        "PublicBusinessIdentity",
                        {
                            "name": serializers.CharField(),
                            "is_active": serializers.BooleanField(),
                        },
                    ),
                    "experience": serializers.CharField(),
                    "branding": inline_serializer(
                        "PublicBranding",
                        {
                            "displayName": serializers.CharField(),
                            "logoUrl": serializers.CharField(allow_blank=True),
                            "primaryColor": serializers.CharField(),
                            "accentColor": serializers.CharField(),
                        },
                    ),
                    "vocabulary": serializers.DictField(child=serializers.CharField()),
                    "policies": inline_serializer(
                        "PublicPolicies",
                        {
                            "timezone": serializers.CharField(),
                            "cancellationWindowHours": serializers.IntegerField(),
                            "requirePhoneOtp": serializers.BooleanField(),
                        },
                    ),
                },
            )
        },
    )
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

    @extend_schema(
        summary="List bookable services",
        responses={200: ServiceSerializer(many=True)},
    )
    def get(self, request):
        services = Service.objects.filter(is_active=True).prefetch_related("staff")
        return Response(ServiceSerializer(services, many=True).data)


class PublicAvailabilityView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        summary="Bookable slots for a service (public)",
        parameters=[AvailabilityQuerySerializer],
        responses={200: AvailabilityResponseSerializer, 404: ErrorResponseSerializer},
    )
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

    @extend_schema(
        summary="Book an appointment as a guest",
        request=GuestBookingSerializer,
        responses={
            201: inline_serializer(
                "PublicBookingCreated",
                {
                    "id": serializers.IntegerField(),
                    "status": serializers.CharField(),
                    "start_at": serializers.DateTimeField(),
                    "end_at": serializers.DateTimeField(),
                    "manage_token": serializers.CharField(
                        help_text="Signed token used to reschedule/cancel later."
                    ),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "Unverified phone or unavailable slot."),
        },
    )
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

    @extend_schema(
        summary="Reschedule or cancel a guest booking (signed token)",
        request=inline_serializer(
            "PublicBookingManageRequest",
            {
                "token": serializers.CharField(help_text="The manage_token from booking."),
                "action": serializers.ChoiceField(choices=["cancel", "reschedule"]),
                "start_at": serializers.DateTimeField(
                    required=False, help_text="Required when action=reschedule."
                ),
            },
        ),
        responses={
            200: inline_serializer(
                "PublicBookingManageResponse",
                {
                    "id": serializers.IntegerField(),
                    "status": serializers.CharField(),
                    "start_at": serializers.DateTimeField(),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "Unknown action / invalid time."),
            404: OpenApiResponse(ErrorResponseSerializer, "Invalid or expired token."),
        },
    )
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


def _services_preview() -> list[dict]:
    services = Service.objects.filter(is_active=True).order_by("name")
    return [
        {
            "id": s.id,
            "name": s.name,
            "durationMinutes": s.duration_minutes,
            "price": str(s.price),
        }
        for s in services
    ]


def _public_hours() -> list[dict]:
    """Business open hours per weekday = the union (min start, max end) of active
    staff's working hours. A simple 'we're open' summary for the page."""
    rows = (
        BusinessHours.objects.filter(staff__is_active=True)
        .values("weekday")
        .annotate(start=Min("start_time"), end=Max("end_time"))
        .order_by("weekday")
    )
    return [
        {
            "weekday": r["weekday"],
            "start": r["start"].strftime("%H:%M"),
            "end": r["end"].strftime("%H:%M"),
        }
        for r in rows
    ]


class PublicPageView(APIView):
    """Everything the public template engine needs to render the booking mini-site
    in one call: the chosen template + branding + content + channels + location +
    (optional) services/hours, plus the accepting-bookings flag."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        summary="Public page payload (template + content for the renderer)",
        responses={
            200: OpenApiResponse(
                OpenApiTypes.OBJECT,
                "template, branding, title, description, cover, channels, location, "
                "services/hours and acceptingBookings.",
            )
        },
    )
    def get(self, request):
        business = request.tenant
        profile = BusinessProfile.get_solo()
        base_vocab = DEFAULT_VOCABULARY.get(business.experience, DEFAULT_VOCABULARY["general"])
        vocabulary = {**base_vocab, **(profile.vocabulary or {})}
        title = profile.display_name or business.name
        return Response(
            {
                "template": profile.template,
                "acceptingBookings": profile.accepting_bookings,
                "business": {
                    "name": business.name,
                    "experience": business.experience,
                    "isActive": business.is_active,
                },
                "branding": {
                    "displayName": title,
                    "logoUrl": profile.logo_url,
                    "primaryColor": profile.primary_color,
                    "accentColor": profile.accent_color,
                },
                "title": title,
                "description": profile.description,
                "coverImageUrl": profile.cover_image_url,
                "channels": profile.channels or {},
                "location": {
                    "latitude": str(profile.latitude) if profile.latitude is not None else None,
                    "longitude": str(profile.longitude) if profile.longitude is not None else None,
                },
                "vocabulary": vocabulary,
                "showServices": profile.show_services,
                "showHours": profile.show_hours,
                "services": _services_preview() if profile.show_services else [],
                "hours": _public_hours() if profile.show_hours else [],
            }
        )
