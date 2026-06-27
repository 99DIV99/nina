"""
SMS OTP verification (new).

This app lives in BOTH the public schema (owner sign-up, on the apex host) and
every tenant schema (customer booking), so the same engine serves both flows with
the schema providing isolation. Codes are stored hashed; never in plain text.
"""

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class OtpPurpose(models.TextChoices):
    SIGNUP = "signup", "Owner sign-up"
    BOOKING = "booking", "Customer booking"
    LOGIN = "login", "Owner passwordless login"


class OtpCode(models.Model):
    # Normalised destination (e.g. 0912xxxxxxx). Not unique: history is kept.
    identifier = models.CharField(max_length=32, db_index=True)
    purpose = models.CharField(max_length=16, choices=OtpPurpose.choices)

    code_hash = models.CharField(max_length=128)  # PBKDF2 hash of the numeric code
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "otp_code"
        indexes = [models.Index(fields=["identifier", "purpose", "created_at"])]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"OTP {self.purpose} -> {self.identifier} ({'used' if self.is_consumed else 'open'})"

    # --- helpers ---
    def set_code(self, code: str) -> None:
        self.code_hash = make_password(code)

    def check_code(self, code: str) -> bool:
        return check_password(code, self.code_hash)

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_locked(self) -> bool:
        return self.attempts >= self.max_attempts
