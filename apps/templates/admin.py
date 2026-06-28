from django.contrib import admin

from apps.templates.models import Template


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "price",
        "is_published",
        "is_featured",
        "sort_order",
        "created_at",
    )
    list_filter = ("is_published", "is_featured")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
