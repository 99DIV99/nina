from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounting.views import InvoiceViewSet, ReportView, TransactionViewSet

app_name = "accounting"

router = DefaultRouter(trailing_slash=False)
router.register("transactions", TransactionViewSet)
router.register("invoices", InvoiceViewSet)

urlpatterns = [
    path("reports/period", ReportView.as_view(), name="report-period"),
    path("", include(router.urls)),
]
