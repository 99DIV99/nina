from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.exceptions import DomainError
from apps.tenancy.models import BusinessType
from apps.tenancy.onboarding import onboard
from apps.tenancy.subdomains import is_available, validate_subdomain


class SubdomainCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raw = request.query_params.get("subdomain", "")
        try:
            normalized = validate_subdomain(raw)
        except DomainError as exc:
            return Response({"available": False, "reason": exc.code, "message": exc.message})
        return Response({"available": is_available(normalized), "subdomain": normalized})


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    full_name = serializers.CharField(max_length=200)
    business_name = serializers.CharField(max_length=200)
    subdomain = serializers.CharField(max_length=16)
    business_type = serializers.ChoiceField(
        choices=BusinessType.choices, default=BusinessType.GENERAL
    )
    phone = serializers.CharField(max_length=32)
    otp_token = serializers.CharField()


class SignupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        from apps.otp.services import check_verification_token

        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        otp_token = data.pop("otp_token")

        # Owner phone is always OTP-verified at sign-up (anti-fraud gate).
        if not check_verification_token(otp_token, data["phone"], "signup"):
            return Response(
                {"error": {"code": "phone_unverified", "message": "Verify your phone first."}},
                status=400,
            )
        try:
            result = onboard(**data)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(result, status=status.HTTP_201_CREATED)
