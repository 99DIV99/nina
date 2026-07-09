# Generated manually - Add payment tracking to Appointment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0002_add_telegram_user_id_to_customer"),
    ]

    operations = [
        # Add PaymentStatus and PaymentMethod choices (implicit in CharField)
        migrations.AddField(
            model_name="appointment",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("unpaid", "Unpaid"),
                    ("partial", "Partial"),
                    ("paid", "Paid"),
                    ("refunded", "Refunded")
                ],
                default="unpaid",
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash", "Cash"),
                    ("card", "Card"),
                    ("transfer", "Bank Transfer"),
                    ("online", "Online Payment")
                ],
                blank=True,
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="payment_amount",
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="payment_notes",
            field=models.TextField(blank=True),
        ),
    ]
