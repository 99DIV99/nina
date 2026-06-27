from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_phone_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="first_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="user",
            name="last_name",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
