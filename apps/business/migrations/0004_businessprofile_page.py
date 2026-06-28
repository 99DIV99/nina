from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0003_businessprofile_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprofile",
            name="template",
            field=models.CharField(default="spotlight", max_length=64),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="description",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="cover_image_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="channels",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="show_services",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="show_hours",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="accepting_bookings",
            field=models.BooleanField(default=True),
        ),
    ]
