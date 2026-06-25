from django.urls import path

from apps.otp.views import RequestOtpView, VerifyOtpView

app_name = "otp"

urlpatterns = [
    path("request", RequestOtpView.as_view(), name="request"),
    path("verify", VerifyOtpView.as_view(), name="verify"),
]
