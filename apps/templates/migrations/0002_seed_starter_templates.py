from django.db import migrations

STARTERS = [
    {
        "slug": "spotlight",
        "name": "Spotlight",
        "description": "Minimal, centered link-in-bio.",
        "sort_order": 1,
    },
    {
        "slug": "storefront",
        "name": "Storefront",
        "description": "Classic website: cover hero + two columns.",
        "sort_order": 2,
    },
    {
        "slug": "lumen",
        "name": "Lumen",
        "description": "Premium cinematic hero, gallery and sticky booking.",
        "sort_order": 3,
        "is_featured": True,
    },
]


def seed(apps, schema_editor):
    Template = apps.get_model("templates", "Template")
    for row in STARTERS:
        Template.objects.update_or_create(slug=row["slug"], defaults=row)


def unseed(apps, schema_editor):
    Template = apps.get_model("templates", "Template")
    Template.objects.filter(slug__in=[r["slug"] for r in STARTERS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("templates", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
