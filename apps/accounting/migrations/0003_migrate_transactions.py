# Generated manually - Migrate existing Transaction data to Income/Expense models

from django.db import migrations


def migrate_transactions(apps, schema_editor):
    """Migrate existing Transaction records to Income and Expense models."""
    Transaction = apps.get_model("accounting", "Transaction")
    Income = apps.get_model("accounting", "Income")
    Expense = apps.get_model("accounting", "Expense")
    IncomeCategory = apps.get_model("accounting", "IncomeCategory")
    ExpenseCategory = apps.get_model("accounting", "ExpenseCategory")

    # Create default "Uncategorized" categories if they don't exist
    default_income_cat, _ = IncomeCategory.objects.get_or_create(
        name="Uncategorized",
        defaults={"description": "Default category for migrated income records"}
    )
    default_expense_cat, _ = ExpenseCategory.objects.get_or_create(
        name="Uncategorized",
        defaults={"description": "Default category for migrated expense records"}
    )

    # Migrate income transactions
    for txn in Transaction.objects.filter(type="income"):
        # Try to find existing category by name, otherwise use default
        category = None
        if txn.category:
            category = IncomeCategory.objects.filter(name=txn.category).first()
            if not category:
                # Create new category from the text
                category, _ = IncomeCategory.objects.get_or_create(
                    name=txn.category,
                    defaults={"description": f"Migrated category: {txn.category}"}
                )
        else:
            category = default_income_cat

        Income.objects.create(
            amount=txn.amount,
            category=category,
            description=txn.description,
            occurred_on=txn.occurred_on,
            source_appointment_id=txn.source_appointment_id,
            payment_method="cash",  # Default for migrated records
        )

    # Migrate expense transactions
    for txn in Transaction.objects.filter(type="expense"):
        # Try to find existing category by name, otherwise use default
        category = None
        if txn.category:
            category = ExpenseCategory.objects.filter(name=txn.category).first()
            if not category:
                # Create new category from the text
                category, _ = ExpenseCategory.objects.get_or_create(
                    name=txn.category,
                    defaults={"description": f"Migrated category: {txn.category}"}
                )
        else:
            category = default_expense_cat

        Expense.objects.create(
            amount=txn.amount,
            category=category,
            description=txn.description,
            occurred_on=txn.occurred_on,
        )


def reverse_migrate(apps, schema_editor):
    """Reverse migration - delete created Income/Expense records."""
    Income = apps.get_model("accounting", "Income")
    Expense = apps.get_model("accounting", "Expense")
    IncomeCategory = apps.get_model("accounting", "IncomeCategory")
    ExpenseCategory = apps.get_model("accounting", "ExpenseCategory")

    # Delete migrated income/expense records
    Income.objects.all().delete()
    Expense.objects.all().delete()

    # Delete the "Uncategorized" categories we created
    IncomeCategory.objects.filter(name="Uncategorized").delete()
    ExpenseCategory.objects.filter(name="Uncategorized").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0002_accounting_refactor"),
    ]

    operations = [
        migrations.RunPython(migrate_transactions, reverse_migrate),
    ]
