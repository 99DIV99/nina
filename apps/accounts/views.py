from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authorization import current_business, current_membership
from apps.accounts.serializers import LoginSerializer, MeSerializer
from apps.accounts.services import register_successful_login


def _tokens_for(user) -> dict:
    # Issuing a refresh token records an OutstandingToken (jti, created/expiry) so
    # tokens can be audited and revoked. That bookkeeping is shared/public data, so
    # mint in the public schema regardless of which host the login arrived on — a
    # tenant schema has no token_blacklist table.
    with schema_context(get_public_schema_name()):
        refresh = RefreshToken.for_user(user)
        return {"access": str(refresh.access_token), "refresh": str(refresh)}


class LoginView(APIView):
    """Issue JWTs. If on a tenant host, require membership in that tenant so a
    token is only minted for someone who actually belongs there."""

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
        return Response(_tokens_for(user))


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
