"""OTP request/verify endpoints. Public (sign-up) + tenant (booking) share these;
the active schema decides which OtpCode table is used."""

from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.api_schema import ErrorResponseSerializer
from apps.common.exceptions import DomainError
from apps.otp.models import OtpPurpose
from apps.otp.services import request_otp, verify_otp


class _RequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    purpose = serializers.ChoiceField(choices=OtpPurpose.choices)


class _VerifySerializer(_RequestSerializer):
    code = serializers.CharField(max_length=12)


PLATFORM_NAME = "نینا"


def _sms_business(request, purpose: str) -> str:
    """The business name for the booking SMS pattern. Sign-up has no business yet
    (its pattern is %code% only), so it returns ""; the purpose is baked into each
    pattern's static text now, not sent as a variable."""
    if purpose != OtpPurpose.BOOKING:
        return ""
    # Tenant schema is active here, so the business_profile table exists.
    from apps.business.models import BusinessProfile

    profile = BusinessProfile.get_solo()
    return profile.display_name or getattr(request.tenant, "name", "") or PLATFORM_NAME


@extend_schema(
    summary="Request an OTP (sign-up or booking verification)",
    request=_RequestSerializer,
    responses={
        201: inline_serializer(
            "OtpRequestResponse",
            {
                "phone": serializers.CharField(),
                "expires_in": serializers.IntegerField(),
            },
        ),
        429: OpenApiResponse(ErrorResponseSerializer, "Cooldown or hourly cap reached."),
    },
)
class RequestOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = _RequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        purpose = ser.validated_data["purpose"]
        business = _sms_business(request, purpose)
        try:
            result = request_otp(ser.validated_data["phone"], purpose, business=business)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(result, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Verify an OTP code and receive a short-lived verification token",
    request=_VerifySerializer,
    responses={
        200: inline_serializer(
            "OtpVerifyResponse",
            {
                "verified": serializers.BooleanField(required=False),
                "token": serializers.CharField(
                    required=False,
                    help_text="Signed token to attach to the matching booking/sign-up call.",
                ),
                "login": serializers.BooleanField(required=False),
                "access": serializers.CharField(required=False),
                "refresh": serializers.CharField(required=False),
            },
        ),
        400: OpenApiResponse(ErrorResponseSerializer, "Invalid or expired code."),
    },
)
class VerifyOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = _VerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            token = verify_otp(
                ser.validated_data["phone"],
                ser.validated_data["purpose"],
                ser.validated_data["code"],
            )
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )

        if ser.validated_data["purpose"] == OtpPurpose.SIGNUP:
            from apps.accounts.models import User
            from apps.accounts.services import register_successful_login, tokens_for_user
            from apps.otp.services import normalize_phone

            phone = normalize_phone(ser.validated_data["phone"])
            existing_user = User.objects.filter(phone=phone, is_active=True).first()
            if existing_user is not None:
                register_successful_login(existing_user)
                return Response({"login": True, **tokens_for_user(existing_user)})

        return Response({"verified": True, "token": token})
