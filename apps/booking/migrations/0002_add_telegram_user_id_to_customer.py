# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="telegram_user_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
