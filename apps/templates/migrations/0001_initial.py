from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Template",
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
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("description", models.CharField(blank=True, max_length=300)),
                ("price", models.DecimalField(decimal_places=0, default=0, max_digits=12)),
                ("is_published", models.BooleanField(default=True)),
                ("is_featured", models.BooleanField(default=False)),
                ("thumbnail_url", models.URLField(blank=True)),
                ("gallery", models.JSONField(blank=True, default=list)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "page_template",
                "ordering": ("sort_order", "created_at"),
            },
        ),
    ]
