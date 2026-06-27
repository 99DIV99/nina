from django.db import migrations, models


class Migration(migrations.Migration):
    """One phone == one account (one business). Partial unique: enforced only when
    `phone` is set, so phone-less accounts (operators/superusers) can coexist."""

    dependencies = [
        ("accounts", "0002_user_is_phone_verified_user_phone"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=("phone",),
                condition=models.Q(phone__gt=""),
                name="uniq_user_phone_when_set",
            ),
        ),
    ]
