from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.authorization import current_membership, effective_permissions
from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "is_email_verified", "is_staff")
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        request = self.context["request"]
        # Resolve the user first to apply lockout even on wrong password.
        email = attrs["email"].lower()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            user = None

        if user and user.is_locked:
            raise serializers.ValidationError(
                "Account temporarily locked due to failed attempts.", code="account_locked"
            )

        auth_user = authenticate(request, username=email, password=attrs["password"])
        if auth_user is None:
            from apps.accounts.services import register_failed_login

            if user:
                register_failed_login(user)
            raise serializers.ValidationError("Invalid credentials.", code="invalid_credentials")

        if not auth_user.is_active:
            raise serializers.ValidationError("Account is disabled.", code="account_disabled")

        attrs["user"] = auth_user
        return attrs


class MeSerializer(serializers.Serializer):
    """Authenticated identity + tenant-scoped role/permissions (derived server-side)."""

    user = UserSerializer()
    role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_role(self, obj):
        membership = current_membership(self.context["request"])
        return membership.role if membership else None

    def get_permissions(self, obj):
        return sorted(effective_permissions(self.context["request"]))
