from django.urls import path

from apps.tenancy.views_operator import TenantActionView, TenantListView

app_name = "operator"

urlpatterns = [
    path("tenants", TenantListView.as_view(), name="tenant-list"),
    path("tenants/<int:pk>/actions", TenantActionView.as_view(), name="tenant-action"),
]
