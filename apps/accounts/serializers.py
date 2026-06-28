from rest_framework import serializers

from apps.accounts.authorization import current_membership, effective_permissions
from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "phone",
            "is_email_verified",
            "is_phone_verified",
            "is_staff",
        )
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """Classic login: phone + password. (The passwordless SMS-code flow is the
    primary login; this is the secondary, credential-based one.)"""

    phone = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        from apps.otp.services import normalize_phone

        phone = normalize_phone(attrs["phone"])
        # Resolve the user first to apply lockout even on a wrong password.
        user = User.objects.filter(phone=phone).first()

        if user and user.is_locked:
            raise serializers.ValidationError(
                "Account temporarily locked due to failed attempts.", code="account_locked"
            )

        if user is None or not user.check_password(attrs["password"]):
            from apps.accounts.services import register_failed_login

            if user:
                register_failed_login(user)
            raise serializers.ValidationError("Invalid credentials.", code="invalid_credentials")

        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.", code="account_disabled")

        attrs["user"] = user
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    """Set a new password after proving phone ownership via an OTP token."""

    phone = serializers.CharField()
    otp_token = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)


class ChangePhoneSerializer(serializers.Serializer):
    """Move the account to a new phone number, OTP-verified on that new number."""

    phone = serializers.CharField()
    otp_token = serializers.CharField()


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
