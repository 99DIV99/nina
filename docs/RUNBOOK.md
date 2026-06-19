# Runbook

## DNS / TLS (production)

Tenants are subdomains of `BASE_DOMAIN`. Requires:
- **Wildcard DNS:** `*.yourapp.com -> app ingress`.
- **Wildcard TLS:** a `*.yourapp.com` certificate (plus per-tenant certs for
  custom domains, provisioned on custom-domain onboarding).

## Migrations

```bash
# Shared (public) schema — run first.
python manage.py migrate_schemas --shared
# All tenant schemas.
python manage.py migrate_schemas
```

New tenants get tenant migrations automatically at provisioning.

## Local Postgres without Docker

If Docker is unavailable, run a throwaway cluster you own:

```bash
PGBIN=/usr/lib/postgresql/14/bin
$PGBIN/initdb -D .pgdata -U nina --auth=trust
$PGBIN/pg_ctl -D .pgdata -o "-p 5433 -k /tmp" -l /tmp/pg.log start
$PGBIN/psql -h /tmp -p 5433 -U nina -d postgres -c "CREATE DATABASE nina OWNER nina;"
# .env: POSTGRES_HOST=/tmp  POSTGRES_PORT=5433
```

## Telegram bot per business (opt-in)

1. The business creates a bot with @BotFather and gets a token.
2. In the panel: `POST /api/v1/bots/{id}/telegram/connect` with
   `{ "telegram_bot_token": "<token>" }`. This registers the per-tenant webhook
   (`https://<tenant>.yourapp.com/api/v1/bots/telegram/webhook`) with a secret
   token Telegram echoes back for verification.
3. Inbound updates are tenant-scoped by host + secret; replies go out via the
   business's own token.

## Email deliverability

Configure SPF, DKIM, and DMARC for the sending domain. Set `EMAIL_BACKEND` and
provider credentials via env. Failed sends retry with backoff then dead-letter in
`notifications_log`.

## Incident: suspected cross-tenant leak

1. This should be impossible — the isolation suite is a permanent gate. If
   suspected, run `pytest apps/tenancy/tests/test_isolation.py` against the
   affected env first.
2. Check `TenantMainMiddleware` is still first in `MIDDLEWARE`.
3. Inspect the audit log in the affected tenant schema.

## Backups & DR

Automated nightly `pg_dump` (or managed snapshots). Per-tenant restore: dump and
restore a single schema (`pg_dump -n <schema>`). Test the restore runbook
quarterly.
