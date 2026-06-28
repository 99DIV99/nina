from django.urls import path

from apps.accounts.views import (
    ChangePhoneView,
    LogoutView,
    MeView,
    OtpLoginRequestView,
    OtpLoginVerifyView,
    PasswordLoginView,
    PasswordResetView,
    RefreshView,
)

app_name = "accounts"

urlpatterns = [
    # Password login (secondary): phone + password.
    path("login", PasswordLoginView.as_view(), name="login"),
    # OTP login (primary, passwordless): request the code, then verify it.
    path("otp/request", OtpLoginRequestView.as_view(), name="otp-login-request"),
    path("otp/verify", OtpLoginVerifyView.as_view(), name="otp-login-verify"),
    # Account self-service (OTP-gated): forgot/reset password + change phone.
    path("password/reset", PasswordResetView.as_view(), name="password-reset"),
    path("phone", ChangePhoneView.as_view(), name="change-phone"),
    path("refresh", RefreshView.as_view(), name="refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
]
