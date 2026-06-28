from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0004_businessprofile_page"),
    ]

    operations = [
        migrations.CreateModel(
            name="PageView",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("visitor_hash", models.CharField(db_index=True, max_length=64)),
                ("ref", models.CharField(blank=True, max_length=40)),
            ],
            options={
                "db_table": "page_view",
            },
        ),
    ]
