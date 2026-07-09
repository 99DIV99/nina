# Generated manually - Accounting module refactor

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        # Create PaymentMethod and PaymentStatus choices first (as text choices are implicit)
        # Then create the new models

        # IncomeCategory model
        migrations.CreateModel(
            name="IncomeCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name_plural": "Income categories",
                "ordering": ("name",),
                "db_table": "accounting_income_category",
            },
        ),

        # ExpenseCategory model
        migrations.CreateModel(
            name="ExpenseCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name_plural": "Expense categories",
                "ordering": ("name",),
                "db_table": "accounting_expense_category",
            },
        ),

        # Income model
        migrations.CreateModel(
            name="Income",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("description", models.TextField(blank=True)),
                ("occurred_on", models.DateField()),
                ("source_appointment_id", models.BigIntegerField(null=True, blank=True, unique=True)),
                ("payment_method", models.CharField(
                    choices=[("cash", "Cash"), ("card", "Card"), ("transfer", "Bank Transfer"), ("online", "Online Payment")],
                    default="cash",
                    max_length=20
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(
                    null=True,
                    blank=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="incomes",
                    to="accounting.incomecategory"
                )),
            ],
            options={
                "ordering": ("-occurred_on", "-created_at"),
                "db_table": "accounting_income",
            },
        ),

        # Add unique constraint to Income
        migrations.AddConstraint(
            model_name="income",
            constraint=models.UniqueConstraint(
                fields=["source_appointment_id"],
                condition=models.Q(source_appointment_id__isnull=False),
                name="uniq_income_per_appointment",
            ),
        ),

        # Expense model
        migrations.CreateModel(
            name="Expense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("description", models.TextField(blank=True)),
                ("occurred_on", models.DateField()),
                ("is_recurring", models.BooleanField(default=False)),
                ("receipt_url", models.URLField(blank=True)),
                ("vendor", models.CharField(max_length=200, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="expenses",
                    to="accounting.expensecategory"
                )),
            ],
            options={
                "ordering": ("-occurred_on", "-created_at"),
                "db_table": "accounting_expense",
            },
        ),

        # Add payment tracking fields to Invoice
        migrations.AddField(
            model_name="invoice",
            name="payment_status",
            field=models.CharField(
                choices=[("unpaid", "Unpaid"), ("partial", "Partial"), ("paid", "Paid"), ("refunded", "Refunded")],
                default="unpaid",
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="paid_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="invoice",
            name="paid_on",
            field=models.DateField(null=True, blank=True),
        ),
    ]
