from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0005_pageview"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprofile",
            name="address",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
