"""
Identity models -- live in the PUBLIC schema so one account can belong to one or
more tenants (equivalent to django-tenant-users, but explicit and fully under our
control for the authorization layer).

Authorization rule (non-negotiable): the client never asserts its tenant, role,
or permissions. Role is ALWAYS re-derived server-side from `Membership`, scoped
to the tenant resolved from the request host.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, is_email_verified=True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Platform-wide account. `is_staff`/`is_superuser` are PLATFORM-operator flags,
    never tenant roles."""

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=200, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # platform operator console access
    is_email_verified = models.BooleanField(default=False)

    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.email

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    FRONT_DESK = "front_desk", "Front Desk"
    PRACTITIONER = "practitioner", "Practitioner"


class Membership(models.Model):
    """Binds a User to a Business (tenant) with a role. Public schema."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    business = models.ForeignKey(
        "tenancy.Business", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.FRONT_DESK)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_membership"
        unique_together = ("user", "business")

    def __str__(self) -> str:
        return f"{self.user.email}@{self.business.schema_name}:{self.role}"
