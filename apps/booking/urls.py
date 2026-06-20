from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.booking.views import (
    AppointmentViewSet,
    AvailabilityView,
    BusinessHoursViewSet,
    CustomerViewSet,
    ServiceViewSet,
    StaffViewSet,
    TimeOffViewSet,
)

app_name = "booking"

router = DefaultRouter(trailing_slash=False)
router.register("services", ServiceViewSet)
router.register("staff", StaffViewSet)
router.register("customers", CustomerViewSet)
router.register("hours", BusinessHoursViewSet)
router.register("time-off", TimeOffViewSet)
router.register("appointments", AppointmentViewSet)

urlpatterns = [
    path("availability", AvailabilityView.as_view(), name="availability"),
    path("", include(router.urls)),
]
