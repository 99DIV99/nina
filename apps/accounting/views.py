"""Accounting API (B6). Flag-gated + permission-gated."""
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting import services
from apps.accounting.models import Invoice, Transaction, TransactionType
from apps.accounting.serializers import (
    ExpenseCreateSerializer,
    InvoiceSerializer,
    TransactionSerializer,
)
from apps.accounts.authorization import P_ACCOUNTING_MANAGE, P_ACCOUNTING_VIEW
from apps.accounts.permissions import HasPermission


class _AccountingPerm(HasPermission):
    pass


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


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [HasPermission]

    @property
    def required_permission(self):
        return P_ACCOUNTING_VIEW if self.request.method == "GET" else P_ACCOUNTING_MANAGE

    def perform_create(self, serializer):
        serializer.save(number=services.next_invoice_number())


class ReportView(APIView):
    permission_classes = [HasPermission]
    required_permission = P_ACCOUNTING_VIEW

    def get(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if not date_from or not date_to:
            return Response(
                {"error": {"code": "range_required", "message": "date_from and date_to required"}},
                status=400,
            )
        return Response(services.period_report(date_from=date_from, date_to=date_to))
