"""Generated migration for MCP server.

This migration creates the MCPInternalToken and MCPRequestAudit models.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MCPInternalToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("scopes", models.JSONField(default=list)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("is_revoked", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_tokens",
                        to="tenancy.business",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "mcp_internal_token",
                "indexes": [
                    models.Index(fields=["token"]),
                    models.Index(fields=["expires_at"]),
                    models.Index(fields=["tenant", "user"]),
                ],
            },
        ),
        migrations.CreateModel(
            name="MCPRequestAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("source", models.CharField(max_length=20)),
                ("tool_name", models.CharField(blank=True, max_length=100, null=True)),
                ("resource_uri", models.CharField(blank=True, max_length=255, null=True)),
                ("parameters", models.JSONField(blank=True, null=True)),
                ("status", models.CharField(max_length=20)),
                ("duration_ms", models.IntegerField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, null=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mcp_audits",
                        to="tenancy.business",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mcp_audits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="mcp_server.mcpinternaltoken",
                    ),
                ),
            ],
            options={
                "db_table": "mcp_request_audit",
                "indexes": [
                    models.Index(fields=["timestamp"]),
                    models.Index(fields=["tenant", "status"]),
                    models.Index(fields=["tool_name"]),
                ],
            },
        ),
    ]
