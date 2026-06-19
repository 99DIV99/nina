"""
Bookkeeping models (B6) -- per-tenant, flag-gated by Business.has_accounting.
"""

from django.db import models


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
                name="uniq_income_per_appointment",
            )
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.amount} ({self.category})"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounting_invoice"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Invoice {self.number} [{self.status}]"
