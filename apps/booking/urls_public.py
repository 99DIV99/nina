from django.urls import path

from apps.booking.views_public import (
    PublicAvailabilityView,
    PublicBookingCreateView,
    PublicBookingManageView,
    PublicBusinessView,
    PublicPageView,
    PublicPageViewTrack,
    PublicServiceListView,
)

app_name = "booking_public"

urlpatterns = [
    path("page", PublicPageView.as_view(), name="page"),
    path("page/view", PublicPageViewTrack.as_view(), name="page-view"),
    path("business", PublicBusinessView.as_view(), name="business"),
    path("services", PublicServiceListView.as_view(), name="services"),
    path("availability", PublicAvailabilityView.as_view(), name="availability"),
    path("book", PublicBookingCreateView.as_view(), name="book"),
    path("manage", PublicBookingManageView.as_view(), name="manage"),
]
