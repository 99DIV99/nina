"""
Install btree_gist in the PUBLIC schema (a SHARED app migration). The booking
exclusion constraint `no_double_booking` needs btree_gist operator classes; with
django-tenants, `public` is always on the search_path, so installing it once here
makes it available inside every tenant schema.
"""
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_initial"),
    ]

    operations = [
        BtreeGistExtension(),
    ]
