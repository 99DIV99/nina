from django.contrib import admin

from apps.accounts.models import Membership, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "is_staff", "is_superuser", "is_active", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "is_email_verified")
    search_fields = ("email", "full_name")
    readonly_fields = ("date_joined", "last_login")
    exclude = ("password",)  # never edit the password hash as plain text here


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "business__name")
