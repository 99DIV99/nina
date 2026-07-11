from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounting.views import (
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    IncomeCategoryViewSet,
    IncomeViewSet,
    InvoiceViewSet,
    LedgerView,
    ReportView,
    TransactionViewSet,
)

app_name = "accounting"

router = DefaultRouter(trailing_slash=False)
router.register("transactions", TransactionViewSet)
router.register("invoices", InvoiceViewSet)
router.register("income", IncomeViewSet, basename="income")
router.register("expense", ExpenseViewSet, basename="expense")
router.register("income-categories", IncomeCategoryViewSet, basename="income-category")
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")

urlpatterns = [
    path("ledger", LedgerView.as_view(), name="ledger"),
    path("reports/period", ReportView.as_view(), name="report-period"),
    path("", include(router.urls)),
]
