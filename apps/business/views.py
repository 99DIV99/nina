import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import P_SETTINGS_MANAGE, current_membership
from apps.accounts.permissions import HasPermission, IsTenantMember
from apps.business.context import build_context
from apps.business.models import BusinessProfile, PageView
from apps.business.serializers import BusinessProfileSerializer, PageSettingsSerializer
from apps.common.api_schema import ErrorResponseSerializer
from apps.common.exceptions import DomainError
from apps.tenancy.models import Domain
from apps.tenancy.subdomains import validate_subdomain


class ContextView(APIView):
    """GET /api/v1/context/ — the bootstrap payload for the authenticated member."""

    permission_classes = [IsTenantMember]

    @extend_schema(
        summary="Bootstrap payload for the authenticated member",
        responses={
            200: OpenApiResponse(
                OpenApiTypes.OBJECT,
                "Business, branding, vocabulary, policies, role and permissions.",
            ),
            403: OpenApiResponse(ErrorResponseSerializer, "Not a member of this business."),
        },
    )
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

    @extend_schema(
        summary="Read business profile (branding, vocabulary, policies)",
        responses={200: BusinessProfileSerializer},
    )
    def get(self, request):
        return Response(BusinessProfileSerializer(BusinessProfile.get_solo()).data)

    @extend_schema(
        summary="Update business profile (requires settings.manage)",
        request=BusinessProfileSerializer,
        responses={
            200: BusinessProfileSerializer,
            403: OpenApiResponse(ErrorResponseSerializer, "settings.manage required"),
        },
    )
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


class ChangeSubdomainView(APIView):
    """Change this business's booking subdomain (Settings -> edit subdomain).

    Validates + checks availability, then swaps the primary Domain. The old
    subdomain stops resolving and the new one goes live immediately. The owner is
    on the dashboard host, so their session is unaffected by the change.
    """

    permission_classes = [HasPermission]
    required_permission = P_SETTINGS_MANAGE

    @extend_schema(
        summary="Change the business booking subdomain",
        request=inline_serializer("ChangeSubdomainRequest", {"subdomain": serializers.CharField()}),
        responses={
            200: inline_serializer(
                "ChangeSubdomainResponse",
                {
                    "subdomain": serializers.CharField(),
                    "live_url": serializers.CharField(),
                },
            ),
            400: OpenApiResponse(ErrorResponseSerializer, "Invalid, reserved or taken subdomain."),
        },
    )
    def post(self, request):
        try:
            sub = validate_subdomain(request.data.get("subdomain", ""))
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        business = request.tenant
        host = f"{sub}.{settings.BASE_DOMAIN}"
        if Domain.objects.filter(domain=host).exclude(tenant=business).exists():
            return Response(
                {"error": {"code": "subdomain_taken", "message": "That subdomain is taken."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        primary = Domain.objects.filter(tenant=business, is_primary=True).first()
        if primary is None:
            Domain.objects.create(tenant=business, domain=host, is_primary=True)
        elif primary.domain != host:
            primary.domain = host
            primary.save(update_fields=["domain"])
        return Response({"subdomain": sub, "live_url": f"https://{host}"})


class PageSettingsView(APIView):
    """Read/update the public-page ('Your Page') settings: template, content,
    branding and location. Reads are open to any member; writes need settings.manage.
    (Scheduling policies + security stay on Settings / BusinessProfileView.)"""

    permission_classes = [IsTenantMember]

    @extend_schema(
        summary="Read Your Page settings",
        responses={200: PageSettingsSerializer},
    )
    def get(self, request):
        return Response(PageSettingsSerializer(BusinessProfile.get_solo()).data)

    @extend_schema(
        summary="Update Your Page settings (requires settings.manage)",
        request=PageSettingsSerializer,
        responses={
            200: PageSettingsSerializer,
            403: OpenApiResponse(ErrorResponseSerializer, "settings.manage required"),
        },
    )
    def patch(self, request):
        self.required_permission = P_SETTINGS_MANAGE
        if not HasPermission().has_permission(request, self):
            return Response(
                {"error": {"code": "forbidden", "message": "settings.manage required"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = BusinessProfile.get_solo()
        serializer = PageSettingsSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PageAnalyticsView(APIView):
    """Public-page analytics: total views + unique visitors + a daily series for the
    trend sparkline. Cookieless and PII-free (see apps.business.analytics)."""

    permission_classes = [IsTenantMember]

    @extend_schema(
        summary="Your Page analytics (views, visitors, trend)",
        parameters=[
            OpenApiParameter("range", int, description="Window in days: 7, 30 (default) or 90.")
        ],
        responses={
            200: inline_serializer(
                "PageAnalytics",
                {
                    "range": serializers.IntegerField(),
                    "views": serializers.IntegerField(),
                    "visitors": serializers.IntegerField(),
                    "series": serializers.ListField(
                        child=inline_serializer(
                            "PageAnalyticsDay",
                            {
                                "date": serializers.CharField(),
                                "views": serializers.IntegerField(),
                                "visitors": serializers.IntegerField(),
                            },
                        )
                    ),
                },
            )
        },
    )
    def get(self, request):
        raw = request.query_params.get("range", "")
        days = int(raw) if raw.isdigit() else 30
        if days not in (7, 30, 90):
            days = 30
        since = timezone.now() - timedelta(days=days)
        qs = PageView.objects.filter(created_at__gte=since)
        series = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(views=Count("id"), visitors=Count("visitor_hash", distinct=True))
            .order_by("day")
        )
        return Response(
            {
                "range": days,
                "views": qs.count(),
                "visitors": qs.values("visitor_hash").distinct().count(),
                "series": [
                    {"date": str(r["day"]), "views": r["views"], "visitors": r["visitors"]}
                    for r in series
                ],
            }
        )


class LogoUploadView(APIView):
    """Upload a business logo: validated + re-encoded to WebP + resized, stored on
    the media volume (namespaced by tenant schema), returns the public URL."""

    permission_classes = [HasPermission]
    required_permission = P_SETTINGS_MANAGE
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Upload a logo (JPG/PNG/WebP, max 10 MB)",
        request=inline_serializer("LogoUpload", {"file": serializers.ImageField()}),
        responses={
            200: inline_serializer("LogoUploadResponse", {"url": serializers.CharField()}),
            400: OpenApiResponse(ErrorResponseSerializer, "Invalid / too large / unsupported."),
        },
    )
    def post(self, request):
        from apps.business.images import process_logo

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {"error": {"code": "no_file", "message": "No file uploaded."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            content = process_logo(uploaded)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        data = content.read()
        digest = hashlib.sha1(data).hexdigest()[:12]  # content hash -> immutable URL
        profile = BusinessProfile.get_solo()
        if profile.logo:
            profile.logo.delete(save=False)  # drop the old file (no orphan/leak)
        profile.logo.save(f"logo_{digest}.webp", ContentFile(data), save=True)
        return Response({"url": profile.logo.url})
