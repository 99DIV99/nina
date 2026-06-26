"""OTP request/verify endpoints. Public (sign-up) + tenant (booking) share these;
the active schema decides which OtpCode table is used."""

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.exceptions import DomainError
from apps.otp.models import OtpPurpose
from apps.otp.services import request_otp, verify_otp


class _RequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    purpose = serializers.ChoiceField(choices=OtpPurpose.choices)


class _VerifySerializer(_RequestSerializer):
    code = serializers.CharField(max_length=12)


_ACTION = {OtpPurpose.BOOKING: "رزرو نوبت", OtpPurpose.SIGNUP: "ثبت‌نام"}
PLATFORM_NAME = "نینا"


def _sms_context(request, purpose: str) -> tuple[str, str]:
    """(business, action) for the SMS pattern. For bookings the business is the
    tenant; for sign-up there's no business yet, so we use the platform name."""
    action = _ACTION.get(purpose, "")
    business = PLATFORM_NAME
    if purpose == OtpPurpose.BOOKING:
        # Tenant schema is active here, so the business_profile table exists.
        from apps.business.models import BusinessProfile

        profile = BusinessProfile.get_solo()
        business = profile.display_name or getattr(request.tenant, "name", "") or PLATFORM_NAME
    return business, action


class RequestOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = _RequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        purpose = ser.validated_data["purpose"]
        business, action = _sms_context(request, purpose)
        try:
            result = request_otp(
                ser.validated_data["phone"], purpose, business=business, action=action
            )
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(result, status=status.HTTP_201_CREATED)


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
        return Response({"verified": True, "token": token})
