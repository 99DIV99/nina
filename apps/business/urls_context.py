from django.urls import path

from apps.business.views import BusinessProfileView, ChangeSubdomainView, ContextView

app_name = "business"

urlpatterns = [
    path("", ContextView.as_view(), name="context"),
    path("profile", BusinessProfileView.as_view(), name="profile"),
    path("subdomain", ChangeSubdomainView.as_view(), name="change-subdomain"),
]
