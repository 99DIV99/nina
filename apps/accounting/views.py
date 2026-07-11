"""Accounting API (B6). Flag-gated + permission-gated."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from datetime import date

from rest_framework import serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting import services
from apps.accounting.models import Expense, ExpenseCategory, Income, IncomeCategory, Invoice, Transaction
from apps.accounting.renderers import CSVRenderer
from apps.accounting.serializers import (
    ExpenseCategorySerializer,
    ExpenseCreateSerializer,
    ExpenseSerializer,
    IncomeCategorySerializer,
    IncomeSerializer,
    InvoiceSerializer,
    TransactionSerializer,
)
from apps.accounts.authorization import P_ACCOUNTING_MANAGE, P_ACCOUNTING_VIEW
from apps.accounts.permissions import HasPermission
from apps.common.api_schema import ErrorResponseSerializer
from apps.common.pagination import DefaultPagination


class _AccountingPerm(HasPermission):
    pass


class _AccountingViewSet(viewsets.ModelViewSet):
    """Use accounting.view for reads and accounting.manage for writes."""

    permission_classes = [HasPermission]

    @property
    def required_permission(self):
        return P_ACCOUNTING_VIEW if self.request.method in ("GET", "HEAD", "OPTIONS") else P_ACCOUNTING_MANAGE


class _CSVListMixin:
    renderer_classes = [CSVRenderer, *APIView.renderer_classes]
    csv_filename = "accounting-export"

    def list(self, request, *args, **kwargs):
        if request.accepted_renderer.format == "csv":
            serializer = self.get_serializer(self.filter_queryset(self.get_queryset()), many=True)
            return Response(serializer.data)
        return super().list(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(
        summary="List transactions (filter by type)",
        parameters=[
            OpenApiParameter(
                "type", str, description="Filter by transaction type, e.g. income|expense."
            )
        ],
    ),
    create=extend_schema(
        summary="Record a manual expense (income is automatic)",
        request=ExpenseCreateSerializer,
        responses={201: TransactionSerializer, 400: ErrorResponseSerializer},
    ),
)
class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [HasPermission]
    http_method_names = ["get", "post", "delete", "head", "options"]

    @property
    def required_permission(self):
        return P_ACCOUNTING_VIEW if self.request.method == "GET" else P_ACCOUNTING_MANAGE

    def get_queryset(self):
        qs = super().get_queryset()
        t = self.request.query_params.get("type")
        if t:
            qs = qs.filter(type=t)
        return qs

    def create(self, request, *args, **kwargs):
        # Only manual EXPENSE creation is allowed via the API; income is automatic.
        ser = ExpenseCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        txn = services.add_expense(**ser.validated_data)
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)


class InvoiceViewSet(_AccountingViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    def perform_create(self, serializer):
        serializer.save(number=services.next_invoice_number())


class IncomeViewSet(_CSVListMixin, _AccountingViewSet):
    queryset = Income.objects.select_related("category")
    serializer_class = IncomeSerializer
    pagination_class = DefaultPagination
    http_method_names = ["get", "post", "delete", "head", "options"]
    csv_filename = "income"

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("date_from"):
            qs = qs.filter(occurred_on__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(occurred_on__lte=params["date_to"])
        if params.get("category"):
            qs = qs.filter(category_id=params["category"])
        if params.get("payment_method"):
            qs = qs.filter(payment_method=params["payment_method"])
        if params.get("staff_id"):
            from apps.booking.models import Appointment

            qs = qs.filter(source_appointment_id__in=Appointment.objects.filter(
                staff_id=params["staff_id"]
            ).values("id"))
        return qs


class ExpenseViewSet(_CSVListMixin, _AccountingViewSet):
    queryset = Expense.objects.select_related("category")
    serializer_class = ExpenseSerializer
    pagination_class = DefaultPagination
    csv_filename = "expenses"

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("date_from"):
            qs = qs.filter(occurred_on__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(occurred_on__lte=params["date_to"])
        if params.get("category"):
            qs = qs.filter(category_id=params["category"])
        if params.get("is_recurring") is not None:
            recurring = params["is_recurring"].lower()
            if recurring in ("true", "1"):
                qs = qs.filter(is_recurring=True)
            elif recurring in ("false", "0"):
                qs = qs.filter(is_recurring=False)
        if params.get("vendor"):
            qs = qs.filter(vendor__icontains=params["vendor"])
        return qs


class IncomeCategoryViewSet(_AccountingViewSet):
    queryset = IncomeCategory.objects.all()
    serializer_class = IncomeCategorySerializer


class ExpenseCategoryViewSet(_AccountingViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer


class LedgerView(_CSVListMixin, APIView):
    permission_classes = [HasPermission]
    required_permission = P_ACCOUNTING_VIEW
    csv_filename = "ledger"

    def get(self, request):
        type_filter = request.query_params.get("type", "all")
        if type_filter not in ("all", "income", "expense"):
            return Response(
                {"error": {"code": "invalid_type", "message": "type must be all, income, or expense"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = list(services.get_ledger(
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            type_filter=type_filter,
        ))
        return Response(rows)


class _ReportView(APIView):
    """Base for date-range accounting reports with JSON or CSV representations."""

    permission_classes = [HasPermission]
    required_permission = P_ACCOUNTING_VIEW
    renderer_classes = [CSVRenderer, *APIView.renderer_classes]
    csv_filename = "report"
    rows_key = None

    def get_dates(self, request):
        raw_from = request.query_params.get("date_from")
        raw_to = request.query_params.get("date_to")
        if not raw_from or not raw_to:
            return None, Response(
                {"error": {"code": "range_required", "message": "date_from and date_to required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            date_from, date_to = date.fromisoformat(raw_from), date.fromisoformat(raw_to)
        except ValueError:
            return None, Response(
                {"error": {"code": "invalid_date", "message": "Dates must use YYYY-MM-DD"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_from > date_to:
            return None, Response(
                {"error": {"code": "invalid_range", "message": "date_from must not be after date_to"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return (date_from, date_to), None

    def get(self, request):
        dates, error = self.get_dates(request)
        if error:
            return error
        report = self.build(*dates)
        if request.accepted_renderer.format == "csv":
            rows = report[self.rows_key] if self.rows_key else [report]
            return Response(rows)
        return Response(report)


class TrendReportView(_ReportView):
    entry_type = None
    interval = None

    def build(self, date_from, date_to):
        return services.trend_report(
            entry_type=self.entry_type, interval=self.interval, date_from=date_from, date_to=date_to
        )

    @property
    def rows_key(self):
        return self.entry_type


class PnLReportView(_ReportView):
    csv_filename = "profit-and-loss"

    def build(self, date_from, date_to):
        return services.period_report(date_from=date_from, date_to=date_to)


class StaffReportView(_ReportView):
    csv_filename = "staff-performance"
    rows_key = "staff"

    def build(self, date_from, date_to):
        return services.staff_report(date_from=date_from, date_to=date_to)


class ServiceReportView(_ReportView):
    csv_filename = "service-profitability"
    rows_key = "services"

    def build(self, date_from, date_to):
        return services.service_report(date_from=date_from, date_to=date_to)


class OutstandingInvoicesView(_ReportView):
    csv_filename = "outstanding-invoices"
    rows_key = "invoices"

    def build(self, date_from, date_to):
        return services.outstanding_invoices(date_from=date_from, date_to=date_to)


class CashFlowView(_ReportView):
    csv_filename = "cash-flow"
    rows_key = "cash_flow"

    def build(self, date_from, date_to):
        return services.cash_flow_report(date_from=date_from, date_to=date_to)


@extend_schema(
    summary="Income / expense / net for a date range",
    parameters=[
        OpenApiParameter(
            "date_from", OpenApiTypes.DATE, required=True, description="Range start (inclusive)."
        ),
        OpenApiParameter(
            "date_to", OpenApiTypes.DATE, required=True, description="Range end (inclusive)."
        ),
    ],
    responses={
        200: inline_serializer(
            "PeriodReport",
            {
                "date_from": serializers.CharField(),
                "date_to": serializers.CharField(),
                "income": serializers.CharField(),
                "expense": serializers.CharField(),
                "net": serializers.CharField(),
            },
        ),
        400: ErrorResponseSerializer,
    },
)
class ReportView(PnLReportView):
    """Compatibility endpoint for the original period profit-and-loss report."""

    csv_filename = "period-report"
