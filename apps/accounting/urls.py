from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounting.views import (
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    CashFlowView,
    IncomeCategoryViewSet,
    IncomeViewSet,
    InvoiceViewSet,
    LedgerView,
    OutstandingInvoicesView,
    PnLReportView,
    ReportView,
    ServiceReportView,
    StaffReportView,
    TransactionViewSet,
    TrendReportView,
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
    path("reports/daily-income", TrendReportView.as_view(entry_type="income", interval="daily", csv_filename="daily-income"), name="daily-income"),
    path("reports/weekly-income", TrendReportView.as_view(entry_type="income", interval="weekly", csv_filename="weekly-income"), name="weekly-income"),
    path("reports/monthly-income", TrendReportView.as_view(entry_type="income", interval="monthly", csv_filename="monthly-income"), name="monthly-income"),
    path("reports/daily-expenses", TrendReportView.as_view(entry_type="expense", interval="daily", csv_filename="daily-expenses"), name="daily-expenses"),
    path("reports/weekly-expenses", TrendReportView.as_view(entry_type="expense", interval="weekly", csv_filename="weekly-expenses"), name="weekly-expenses"),
    path("reports/monthly-expenses", TrendReportView.as_view(entry_type="expense", interval="monthly", csv_filename="monthly-expenses"), name="monthly-expenses"),
    path("reports/pnl", PnLReportView.as_view(), name="report-pnl"),
    path("reports/staff", StaffReportView.as_view(), name="report-staff"),
    path("reports/services", ServiceReportView.as_view(), name="report-services"),
    path("reports/outstanding", OutstandingInvoicesView.as_view(), name="report-outstanding"),
    path("reports/cash-flow", CashFlowView.as_view(), name="report-cash-flow"),
    path("", include(router.urls)),
]
