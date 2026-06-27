from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authorization import current_business, current_membership
from apps.accounts.models import User
from apps.accounts.serializers import LoginSerializer, MeSerializer
from apps.accounts.services import register_successful_login, tokens_for_user
from apps.common.exceptions import DomainError
from apps.otp.models import OtpPurpose
from apps.otp.services import normalize_phone, request_otp, verify_otp


class PasswordLoginView(APIView):
    """Password login (the secondary method): email + password -> JWTs. On a tenant
    host, require membership in that tenant so a token is only minted for someone who
    actually belongs there. The primary method is OtpLoginRequest/Verify below."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

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

    def post(self, request):
        # Stateless JWT: client discards tokens. (Blacklist app can be added later.)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Lightweight identity echo. The rich bootstrap payload is /api/v1/context/."""

    permission_classes = [IsAuthenticated]

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
