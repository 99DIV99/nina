"""Generated migration for MCP server.

This migration creates the MCPInternalToken and MCPRequestAudit models.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenant", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MCPInternalToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("scopes", models.ArrayField(models.CharField(max_length=50), null=True)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("used_at", models.DateTimeField(null=True)),
                ("is_revoked", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_tokens",
                        to="tenant.tenant",
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
                "db_table": "mcp_internal_tokens",
                "indexes": [
                    models.Index(fields=["tenant", "expires_at"]),
                    models.Index(fields=["created_at"]),
                ],
            },
        ),
        migrations.CreateModel(
            name="MCPRequestAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(max_length=20)),
                ("tool_name", models.CharField(max_length=100)),
                ("resource_uri", models.CharField(max_length=255, null=True)),
                ("status", models.CharField(max_length=20)),
                ("duration_ms", models.IntegerField(null=True)),
                ("error_message", models.TextField(null=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mcp_audits",
                        to="tenant.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mcp_audits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "mcp_request_audits",
                "indexes": [
                    models.Index(fields=["tenant", "-timestamp"]),
                    models.Index(fields=["user", "-timestamp"]),
                    models.Index(fields=["tool_name"]),
                ],
            },
        ),
    ]
