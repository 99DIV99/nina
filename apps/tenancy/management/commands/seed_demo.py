"""Seed a demo tenant so you can poke the API locally: `manage.py seed_demo`."""
from django.core.management.base import BaseCommand

from apps.tenancy.models import BusinessType
from apps.tenancy.onboarding import onboard


class Command(BaseCommand):
    help = "Create a demo barber tenant with an owner account."

    def handle(self, *args, **options):
        from apps.accounts.models import User
        from apps.tenancy.models import Domain

        if Domain.objects.filter(domain="acme.localhost").exists():
            self.stdout.write(self.style.WARNING("acme.localhost already exists; skipping."))
            return
        if User.objects.filter(email="owner@acme.test").exists():
            User.objects.filter(email="owner@acme.test").delete()

        result = onboard(
            email="owner@acme.test",
            password="demo-pass-123",
            full_name="Acme Owner",
            business_name="Acme Barbershop",
            subdomain="acme",
            business_type=BusinessType.BARBER,
        )
        self.stdout.write(self.style.SUCCESS(f"Seeded: {result}"))
        self.stdout.write("Login: owner@acme.test / demo-pass-123 at http://acme.localhost:8000")
