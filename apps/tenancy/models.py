"""
Tenancy models -- live in the PUBLIC schema.

`Business` is the tenant. Each business gets its own PostgreSQL schema; that
schema is the isolation boundary. Tenant apps carry NO business_id -- isolation
is structural, not a filter column.
"""

from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class BusinessType(models.TextChoices):
    BARBER = "barber", "Barber / Salon"
    CLINIC = "clinic", "Clinic"
    GENERAL = "general", "General"


class PlanTier(models.TextChoices):
    TRIAL = "trial", "Trial"
    STARTER = "starter", "Starter"
    PRO = "pro", "Pro"
    SUSPENDED = "suspended", "Suspended"


class Business(TenantMixin):
    """
    A tenant. `schema_name` (from TenantMixin) names its Postgres schema.

    auto_create_schema=True means saving a new Business provisions its schema and
    runs tenant migrations. We keep it on but drive creation through the
    provisioning service so onboarding stays transactional and validated.
    """

    auto_create_schema = True
    auto_drop_schema = True  # convenient in dev/test; gate behind a flag in prod ops

    name = models.CharField(max_length=200)

    # B3: type drives onboarding defaults; `experience` is DECOUPLED so the
    # frontend vertical can differ from the legal/business type if needed.
    business_type = models.CharField(
        max_length=32, choices=BusinessType.choices, default=BusinessType.GENERAL
    )
    experience = models.CharField(
        max_length=32, choices=BusinessType.choices, default=BusinessType.GENERAL
    )

    plan = models.CharField(max_length=32, choices=PlanTier.choices, default=PlanTier.TRIAL)
    is_active = models.BooleanField(default=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    # --- Feature flags (B3). Source of truth for what a tenant MAY do. ---
    has_booking = models.BooleanField(default=True)
    has_accounting = models.BooleanField(default=False)
    has_records = models.BooleanField(default=False)  # clinical records (special-category)
    has_bots = models.BooleanField(default=False)
    has_sms = models.BooleanField(default=False)

    created_on = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "tenancy_business"

    def __str__(self) -> str:
        return f"{self.name} ({self.schema_name})"

    def apply_type_defaults(self) -> None:
        """Seed feature flags + experience from the chosen business_type (B3)."""
        self.experience = self.business_type
        if self.business_type == BusinessType.CLINIC:
            self.has_accounting = True
            self.has_records = True
        elif self.business_type == BusinessType.BARBER:
            self.has_accounting = True
            self.has_records = False
        else:
            self.has_accounting = False
            self.has_records = False

    def enabled_modules(self) -> list[str]:
        modules = []
        if self.has_booking:
            modules.append("booking")
        if self.has_accounting:
            modules.append("accounting")
        if self.has_records:
            modules.append("records")
        if self.has_bots:
            modules.append("bots")
        return modules


class Domain(DomainMixin):
    """Maps a hostname (subdomain or custom domain) to a Business."""

    is_custom = models.BooleanField(default=False)

    class Meta:
        db_table = "tenancy_domain"
