"""Add PendingAction model for confirmation flow."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0001_initial"),
        ("accounts", "0001_initial"),
        ("mcp_server", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PendingAction",
            fields=[
                ("id", models.CharField(max_length=36, primary_key=True, serialize=False)),
                ("tool_name", models.CharField(max_length=100)),
                ("tool_params", models.JSONField()),
                ("description", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("executed_at", models.DateTimeField(null=True, blank=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to="tenancy.business"
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to="accounts.user"
                )),
            ],
            options={
                "db_table": "mcp_pending_action",
                "indexes": [
                    models.Index(fields=["id"], name="mcp_action_idx"),
                    models.Index(fields=["tenant", "user"], name="mcp_action_user_idx"),
                    models.Index(fields=["expires_at"], name="mcp_action_expires_idx"),
                ],
            },
        ),
    ]
