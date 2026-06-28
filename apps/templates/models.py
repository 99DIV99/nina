"""
Public-page template catalog — a "template store".

GLOBAL and shared across all tenants, so it lives in the PUBLIC schema. A business
picks a template by its SLUG, stored as a plain value on the per-tenant
BusinessProfile (never a cross-schema FK); the slug also maps to the frontend skin
component.

Standalone for now — not surfaced in the UI yet. It's the foundation for a future
store: browsing, premium/paid templates, featured, tags, versions, etc. Everything
is free today (price defaults to 0).
"""

from django.db import models


class Template(models.Model):
    # --- Identity ---
    # The slug maps to the frontend skin component + is stored on BusinessProfile.
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)

    # --- Store / product (everything free for now) ---
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0)  # Toman; 0 == free
    is_published = models.BooleanField(default=True)  # visible in the store
    is_featured = models.BooleanField(default=False)

    # --- Presentation (store grid + detail page) ---
    thumbnail_url = models.URLField(blank=True)
    gallery = models.JSONField(default=list, blank=True)  # extra preview image URLs
    tags = models.JSONField(default=list, blank=True)  # e.g. ["minimal", "barber"]

    # --- Ordering / housekeeping ---
    sort_order = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)  # "date added" to the store
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "page_template"
        ordering = ("sort_order", "created_at")

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    @property
    def is_free(self) -> bool:
        return self.price == 0
