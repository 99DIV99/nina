from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authorization import current_business, current_membership
from apps.accounts.models import User
from apps.accounts.serializers import (
    ChangePhoneSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetSerializer,
)
from apps.accounts.services import register_successful_login, tokens_for_user
from apps.common.api_schema import ErrorResponseSerializer, TokenPairSerializer
from apps.common.exceptions import DomainError
from apps.otp.models import OtpPurpose
from apps.otp.services import check_verification_token, normalize_phone, request_otp, verify_otp


class PasswordLoginView(APIView):
    """Password login (the secondary method): email + password -> JWTs. On a tenant
    host, require membership in that tenant so a token is only minted for someone who
    actually belongs there. The primary method is OtpLoginRequest/Verify below."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="Password login (secondary method)",
        request=LoginSerializer,
        responses={
            200: TokenPairSerializer,
            401: OpenApiResponse(ErrorResponseSerializer, "Invalid credentials."),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        business = current_business(request)
        if business is not None:
            from apps.accounts.models import Membership

            is_member = Membership.objects.filter(
                user=user, business=business, is_active=True
            ).exists()
            if not is_member:
                # Do not reveal whether the account exists for another tenant.
                return Response(
                    {"error": {"code": "invalid_credentials", "message": "Invalid credentials."}},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        register_successful_login(user)
        return Response(tokens_for_user(user))


class RefreshView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Exchange a refresh token for a new access token",
        request=inline_serializer("RefreshRequest", {"refresh": serializers.CharField()}),
        responses={
            200: inline_serializer(
                "RefreshResponse",
                {
                    "access": serializers.CharField(),
                    "refresh": serializers.CharField(required=False),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "refresh token required"),
            401: OpenApiResponse(ErrorResponseSerializer, "invalid refresh token"),
        },
    )
    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response(
                {"error": {"code": "refresh_required", "message": "refresh token required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh = RefreshToken(token)
            data = {"access": str(refresh.access_token)}
            if refresh.token:
                data["refresh"] = str(refresh)
        except Exception:
            return Response(
                {"error": {"code": "invalid_token", "message": "invalid refresh token"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Log out (client discards tokens)",
        request=None,
        responses={204: OpenApiResponse(description="No content.")},
    )
    def post(self, request):
        # Stateless JWT: client discards tokens. (Blacklist app can be added later.)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Lightweight identity echo. The rich bootstrap payload is /api/v1/context/."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Authenticated identity + tenant role/permissions",
        responses={
            200: MeSerializer,
            403: OpenApiResponse(ErrorResponseSerializer, "Not a member of this business."),
        },
    )
    def get(self, request):
        membership = current_membership(request)
        if current_business(request) is not None and membership is None:
            return Response(
                {"error": {"code": "not_a_member", "message": "Not a member of this business."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(MeSerializer({"user": request.user}, context={"request": request}).data)


class OtpLoginRequestView(APIView):
    """OTP login (the PRIMARY, passwordless method) — step 1. Sends a login OTP when
    the phone has an account; otherwise tells the client to sign up. No SMS is spent
    on unknown numbers, and existence is only revealed at this deliberate entry."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="OTP login step 1 — send a login code to a known phone",
        request=inline_serializer("OtpLoginRequest", {"phone": serializers.CharField()}),
        responses={
            200: inline_serializer(
                "OtpLoginRequestResponse",
                {
                    "sent": serializers.BooleanField(),
                    "needs_signup": serializers.BooleanField(required=False),
                    "expires_in": serializers.IntegerField(required=False),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "Enter a valid phone number."),
        },
    )
    def post(self, request):
        phone = normalize_phone(request.data.get("phone", ""))
        if len(phone) < 7:
            return Response(
                {"error": {"code": "invalid_phone", "message": "Enter a valid phone number."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not User.objects.filter(phone=phone, is_active=True).exists():
            return Response({"sent": False, "needs_signup": True})
        try:
            result = request_otp(phone, OtpPurpose.LOGIN)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response({"sent": True, **result})


class OtpLoginVerifyView(APIView):
    """OTP login — step 2: verify the code, then issue tokens. The token is vanilla;
    the dashboard host resolves the business from the user."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="OTP login step 2 — verify the code and receive tokens",
        request=inline_serializer(
            "OtpLoginVerify",
            {"phone": serializers.CharField(), "code": serializers.CharField()},
        ),
        responses={
            200: TokenPairSerializer,
            400: OpenApiResponse(ErrorResponseSerializer, "Invalid or expired code."),
            404: OpenApiResponse(ErrorResponseSerializer, "No account for this number."),
        },
    )
    def post(self, request):
        phone = normalize_phone(request.data.get("phone", ""))
        code = str(request.data.get("code", "")).strip()
        try:
            verify_otp(phone, OtpPurpose.LOGIN, code)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        user = User.objects.filter(phone=phone, is_active=True).first()
        if user is None:
            return Response(
                {
                    "error": {"code": "no_account", "message": "No account for this number."},
                    "needs_signup": True,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        register_successful_login(user)
        return Response(tokens_for_user(user))


class PasswordResetView(APIView):
    """Forgot / reset password: set a new password once an OTP proves the phone.
    Drives the login 'Forgot password?' link AND Settings -> reset password. The
    phone must have been OTP-verified for the 'password_reset' purpose. On success
    the owner is logged straight in (tokens returned)."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="Reset password after phone OTP",
        request=PasswordResetSerializer,
        responses={
            200: TokenPairSerializer,
            400: OpenApiResponse(ErrorResponseSerializer, "Phone not verified."),
            404: OpenApiResponse(ErrorResponseSerializer, "No account for this number."),
        },
    )
    def post(self, request):
        ser = PasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        phone = normalize_phone(data["phone"])
        if not check_verification_token(data["otp_token"], phone, OtpPurpose.PASSWORD_RESET.value):
            return Response(
                {"error": {"code": "phone_unverified", "message": "Verify your phone first."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.filter(phone=phone, is_active=True).first()
        if user is None:
            return Response(
                {"error": {"code": "no_account", "message": "No account for this number."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        user.set_password(data["password"])
        user.is_phone_verified = True
        user.save(update_fields=["password", "is_phone_verified"])
        register_successful_login(user)  # clears any lockout
        return Response(tokens_for_user(user))


class ChangePhoneView(APIView):
    """Move the signed-in account to a new phone number, OTP-verified on the NEW
    number (Settings -> change phone). One phone == one account, so the number must
    be free."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(
        summary="Change the account phone number (OTP-verified)",
        request=ChangePhoneSerializer,
        responses={
            200: inline_serializer("ChangePhoneResponse", {"phone": serializers.CharField()}),
            400: OpenApiResponse(ErrorResponseSerializer, "New number not verified."),
            409: OpenApiResponse(ErrorResponseSerializer, "Number already in use."),
        },
    )
    def post(self, request):
        ser = ChangePhoneSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        new_phone = normalize_phone(ser.validated_data["phone"])
        if not check_verification_token(
            ser.validated_data["otp_token"], new_phone, OtpPurpose.PHONE_CHANGE.value
        ):
            return Response(
                {"error": {"code": "phone_unverified", "message": "Verify the new number first."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(phone=new_phone).exclude(pk=request.user.pk).exists():
            return Response(
                {"error": {"code": "phone_taken", "message": "That number is already in use."}},
                status=status.HTTP_409_CONFLICT,
            )
        user = request.user
        user.phone = new_phone
        user.is_phone_verified = True
        user.save(update_fields=["phone", "is_phone_verified"])
        return Response({"phone": new_phone})
