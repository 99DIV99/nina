"""
TENANT-schema URLconf.

These routes are served when a request resolves to a tenant schema (e.g.
acme.yourapp.com). The schema has already been switched by TenantMainMiddleware,
so everything here operates inside the tenant's isolation boundary.
"""

from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve as serve_media
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.health import healthz, readyz

v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("otp/", include("apps.otp.urls")),  # customer-booking phone verification
    path("context/", include("apps.business.urls_context")),
    path("booking/", include("apps.booking.urls")),
    path("public/", include("apps.booking.urls_public")),
    path("accounting/", include("apps.accounting.urls")),
    path("bots/", include("apps.bots.urls")),
]

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("api/v1/", include((v1, "v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # User-uploaded media (logos). Served by Django at MVP scale; becomes unused
    # once storage moves to an object-storage bucket (URLs point off-box then).
    re_path(r"^media/(?P<path>.*)$", serve_media, {"document_root": settings.MEDIA_ROOT}),
]
