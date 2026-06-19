from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import current_membership
from apps.accounts.permissions import HasPermission, IsTenantMember
from apps.accounts.authorization import P_SETTINGS_MANAGE
from apps.business.context import build_context
from apps.business.models import BusinessProfile
from apps.business.serializers import BusinessProfileSerializer


class ContextView(APIView):
    """GET /api/v1/context/ — the bootstrap payload for the authenticated member."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        if current_membership(request) is None:
            return Response(
                {"error": {"code": "not_a_member", "message": "Not a member of this business."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(build_context(request))


class BusinessProfileView(APIView):
    """Read/update per-tenant branding + vocabulary + policies."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(BusinessProfileSerializer(BusinessProfile.get_solo()).data)

    def patch(self, request):
        # Writes require settings.manage; reads are open to any member.
        self.required_permission = P_SETTINGS_MANAGE
        perm = HasPermission()
        if not perm.has_permission(request, self):
            return Response(
                {"error": {"code": "forbidden", "message": "settings.manage required"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = BusinessProfile.get_solo()
        serializer = BusinessProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
