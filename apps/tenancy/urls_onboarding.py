from django.urls import path

from apps.tenancy.views_onboarding import SignupView, SubdomainCheckView

app_name = "onboarding"

urlpatterns = [
    path("check-subdomain", SubdomainCheckView.as_view(), name="check-subdomain"),
    path("signup", SignupView.as_view(), name="signup"),
]
