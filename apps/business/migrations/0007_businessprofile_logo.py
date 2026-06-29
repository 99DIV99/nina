import apps.business.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0006_businessprofile_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprofile",
            name="logo",
            field=models.ImageField(
                blank=True, upload_to=apps.business.models.logo_upload_path
            ),
        ),
    ]
