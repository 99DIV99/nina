"""
PUBLIC-schema URLconf.

Served on the apex/marketing domain and the `api`/`app` host. No tenant schema
is active here. Onboarding (which creates tenants), the operator console, and
platform billing webhooks live in the public schema.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.health import healthz, readyz

v1 = [
    path("onboarding/", include("apps.tenancy.urls_onboarding")),
    path("auth/", include("apps.accounts.urls")),
    path("operator/", include("apps.tenancy.urls_operator")),
]

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("api/v1/", include((v1, "v1_public"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema-public"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema-public"), name="docs-public"),
]
