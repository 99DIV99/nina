"""
Bookkeeping models (B6) -- per-tenant, flag-gated by Business.has_accounting.
"""

from django.db import models


# =============================================================================
# Payment & Status Choices (shared across models)
# =============================================================================

class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    TRANSFER = "transfer", "Bank Transfer"
    ONLINE = "online", "Online Payment"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PARTIAL = "partial", "Partial"
    PAID = "paid", "Paid"
    REFUNDED = "refunded", "Refunded"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


# =============================================================================
# Categories (per-tenant)
# =============================================================================

class IncomeCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_income_category"
        verbose_name_plural = "Income categories"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_expense_category"
        verbose_name_plural = "Expense categories"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


# =============================================================================
# Income & Expense Models
# =============================================================================

class Income(models.Model):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(
        IncomeCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incomes"
    )
    description = models.TextField(blank=True)
    occurred_on = models.DateField()

    # Link back to the source appointment for auto-income. Unique when present,
    # which makes auto-income idempotent: one completed appointment -> one income
    # row, never double-counted.
    source_appointment_id = models.BigIntegerField(unique=True, null=True, blank=True)

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_income"
        ordering = ("-occurred_on", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["source_appointment_id"],
                condition=models.Q(source_appointment_id__isnull=False),
                name="uniq_income_per_appointment",
            )
        ]

    def __str__(self) -> str:
        category_name = self.category.name if self.category else "No category"
        return f"Income {self.amount} ({category_name}) - {self.occurred_on}"


class Expense(models.Model):
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses"
    )
    description = models.TextField(blank=True)
    occurred_on = models.DateField()
    is_recurring = models.BooleanField(default=False)

    # Optional: store receipt/proof URL
    receipt_url = models.URLField(blank=True)
    vendor = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_expense"
        ordering = ("-occurred_on", "-created_at")

    def __str__(self) -> str:
        return f"Expense {self.amount} ({self.category.name}) - {self.occurred_on}"


# =============================================================================
# Legacy Transaction Model (kept for migration compatibility)
# TODO: Remove after migrating existing data to Income/Expense models
# =============================================================================

class TransactionType(models.TextChoices):
    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"


class Transaction(models.Model):
    type = models.CharField(max_length=10, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255, blank=True)
    occurred_on = models.DateField()

    # Link back to the source appointment for auto-income. Unique when present,
    # which makes auto-income idempotent: one completed appointment -> one income
    # row, never double-counted.
    source_appointment_id = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_transaction"
        ordering = ("-occurred_on", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["source_appointment_id"],
                condition=models.Q(source_appointment_id__isnull=False),
                name="uniq_transaction_per_appointment",
            )
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.amount} ({self.category})"


# =============================================================================
# Invoice Model (updated with payment tracking)
# =============================================================================

class Invoice(models.Model):
    number = models.CharField(max_length=40, unique=True)
    customer_id = models.BigIntegerField(null=True, blank=True)
    appointment_id = models.BigIntegerField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT
    )
    issued_on = models.DateField(null=True, blank=True)
    due_on = models.DateField(null=True, blank=True)

    # Payment tracking
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID
    )
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_on = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_invoice"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Invoice {self.number} [{self.status}]"
