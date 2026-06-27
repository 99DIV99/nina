from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0002_businessprofile_require_phone_otp"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprofile",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True),
        ),
    ]
