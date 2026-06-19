"""
Create the public tenant + its domain so apex/non-tenant hosts resolve to the
PUBLIC_SCHEMA_URLCONF (onboarding, operator, health). Idempotent.

Run once after `migrate_schemas --shared`.
"""
from django.core.management.base import BaseCommand

from apps.tenancy.models import Business, Domain


class Command(BaseCommand):
    help = "Create the public tenant and its domains (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--hosts", nargs="*", default=["localhost", "127.0.0.1"])

    def handle(self, *args, **options):
        public = Business.objects.filter(schema_name="public").first()
        if public is None:
            public = Business(schema_name="public", name="Public", business_type="general")
            public.auto_create_schema = False  # the public schema already exists
            public.save()
            self.stdout.write(self.style.SUCCESS("Created public tenant."))
        else:
            self.stdout.write("Public tenant already exists.")

        for host in options["hosts"]:
            domain, created = Domain.objects.get_or_create(
                domain=host, defaults={"tenant": public, "is_primary": host == options["hosts"][0]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Mapped {host} -> public."))
