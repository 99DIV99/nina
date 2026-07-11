from decimal import Decimal

from rest_framework import serializers

from apps.accounting.models import (
    Expense,
    ExpenseCategory,
    Income,
    IncomeCategory,
    Invoice,
    Transaction,
)


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


class IncomeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeCategory
        fields = ("id", "name", "description", "is_active", "created_at")
        read_only_fields = ("created_at",)


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ("id", "name", "description", "is_active", "created_at")
        read_only_fields = ("created_at",)


class IncomeSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta:
        model = Income
        fields = (
            "id",
            "amount",
            "category",
            "category_name",
            "description",
            "occurred_on",
            "source_appointment_id",
            "payment_method",
            "created_at",
        )
        read_only_fields = ("source_appointment_id", "created_at")


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Expense
        fields = (
            "id",
            "amount",
            "category",
            "category_name",
            "description",
            "occurred_on",
            "is_recurring",
            "receipt_url",
            "vendor",
            "created_at",
        )
        read_only_fields = ("created_at",)


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
