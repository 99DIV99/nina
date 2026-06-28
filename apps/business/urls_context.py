from django.urls import path

from apps.business.views import (
    BusinessProfileView,
    ChangeSubdomainView,
    ContextView,
    PageAnalyticsView,
    PageSettingsView,
)

app_name = "business"

urlpatterns = [
    path("", ContextView.as_view(), name="context"),
    path("profile", BusinessProfileView.as_view(), name="profile"),
    path("page", PageSettingsView.as_view(), name="page"),
    path("page/analytics", PageAnalyticsView.as_view(), name="page-analytics"),
    path("subdomain", ChangeSubdomainView.as_view(), name="change-subdomain"),
]
