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
    subdomain = serializers.CharField(max_length=63)
    business_type = serializers.ChoiceField(
        choices=BusinessType.choices, default=BusinessType.GENERAL
    )


class SignupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = onboard(**serializer.validated_data)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        return Response(result, status=status.HTTP_201_CREATED)
