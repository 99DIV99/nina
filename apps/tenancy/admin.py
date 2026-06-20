from django.contrib import admin

from apps.tenancy.models import Business, Domain


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "schema_name", "business_type", "plan", "is_active", "created_on")
    list_filter = (
        "business_type",
        "plan",
        "is_active",
        "has_accounting",
        "has_bots",
        "has_records",
    )
    search_fields = ("name", "schema_name")
    readonly_fields = ("schema_name", "created_on")


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary", "is_custom")
    list_filter = ("is_primary", "is_custom")
    search_fields = ("domain",)
