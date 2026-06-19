from decimal import Decimal

from rest_framework import serializers

from apps.accounting.models import Invoice, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "id",
            "type",
            "amount",
            "category",
            "description",
            "occurred_on",
            "source_appointment_id",
            "created_at",
        )
        read_only_fields = ("source_appointment_id", "created_at")


class ExpenseCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    category = serializers.CharField(max_length=100)
    description = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    occurred_on = serializers.DateField()


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = (
            "id",
            "number",
            "customer_id",
            "appointment_id",
            "amount",
            "status",
            "issued_on",
            "due_on",
            "created_at",
        )
        read_only_fields = ("number", "created_at")
