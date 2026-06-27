from django.urls import path

from apps.accounts.views import (
    LogoutView,
    MeView,
    OtpLoginRequestView,
    OtpLoginVerifyView,
    PasswordLoginView,
    RefreshView,
)

app_name = "accounts"

urlpatterns = [
    # Password login (secondary).
    path("login", PasswordLoginView.as_view(), name="login"),
    # OTP login (primary, passwordless): request the code, then verify it.
    path("otp/request", OtpLoginRequestView.as_view(), name="otp-login-request"),
    path("otp/verify", OtpLoginVerifyView.as_view(), name="otp-login-verify"),
    path("refresh", RefreshView.as_view(), name="refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
]
