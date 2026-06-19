"""Platform operator console APIs (B8). Public schema; platform-staff only."""
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformOperator
from apps.tenancy.models import Business
from apps.tenancy.provisioning import reactivate, suspend


class BusinessAdminSerializer(serializers.ModelSerializer):
    primary_domain = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = (
            "id", "name", "schema_name", "business_type", "experience", "plan",
            "is_active", "suspended_at", "has_accounting", "has_records",
            "has_bots", "has_sms", "created_on", "primary_domain",
        )

    def get_primary_domain(self, obj):
        d = obj.domains.filter(is_primary=True).first()
        return d.domain if d else None


class TenantListView(ListAPIView):
    permission_classes = [IsPlatformOperator]
    serializer_class = BusinessAdminSerializer

    def get_queryset(self):
        qs = Business.objects.exclude(schema_name="public").order_by("-created_on")
        search = self.request.query_params.get("q")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class TenantActionView(APIView):
    permission_classes = [IsPlatformOperator]

    def post(self, request, pk):
        business = Business.objects.exclude(schema_name="public").filter(pk=pk).first()
        if business is None:
            return Response({"error": {"code": "not_found", "message": "Tenant not found."}}, status=404)
        action = request.data.get("action")
        flags = request.data.get("flags")
        if action == "suspend":
            suspend(business)
        elif action == "reactivate":
            reactivate(business)
        elif action == "set_flags" and isinstance(flags, dict):
            allowed = {"has_accounting", "has_records", "has_bots", "has_sms", "plan"}
            for key, value in flags.items():
                if key in allowed:
                    setattr(business, key, value)
            business.save()
        else:
            return Response({"error": {"code": "bad_action", "message": "Unknown action."}}, status=400)
        return Response(BusinessAdminSerializer(business).data)
