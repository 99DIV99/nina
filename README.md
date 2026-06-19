# NINA — Booking & Bookkeeping SaaS (Backend)

Multi-tenant booking platform. **Schema-per-tenant** on PostgreSQL via
`django-tenants`: one business = one tenant = one Postgres schema, and the schema
*is* the isolation boundary. The backend is a single uniform pipeline for every
business; verticals (barber / clinic / general) differ only in the frontend, which
mounts an experience from the backend's context payload.

## Core principles (enforced, not aspirational)

- **Schema is the isolation boundary.** Tenant tables carry no `business_id`.
- **Server-side authorization is absolute.** The client never asserts its tenant,
  role, type, or permissions — the backend re-derives all of them every request
  from `Membership(user, tenant)`. Forged identity claims are ignored. See
  `apps/accounts/authorization.py`.
- **Booking correctness is non-negotiable.** No double-booking, ever — enforced by
  a Postgres exclusion constraint *and* atomic transactions. Timezone/DST-correct.
- **Feature flags + business type** drive capability, not divergent schemas.
- **Bots are actors, not backdoors.** A bot is scoped to one tenant and books
  through the same authorized service as a human.

## Stack

Python 3.10 · Django 5.0 · DRF · django-tenants · PostgreSQL · Celery/Redis ·
SimpleJWT · drf-spectacular (OpenAPI).

## Quick start (local)

```bash
# From the repo root, the 'nina' virtualenv lives one level up.
cp .env.example .env                      # adjust if needed
../nina/bin/pip install -r requirements/dev.txt

# Postgres + Redis: use docker-compose, OR a local cluster (see RUNBOOK).
docker compose up -d db redis             # if Docker is available

make migrate-shared                       # public schema (shared apps)
../nina/bin/python manage.py seed_demo    # creates acme.localhost + owner
make run                                  # http://localhost:8000
```

Add `127.0.0.1 acme.localhost` to `/etc/hosts` (or use `*.localhost`, which most
resolvers send to loopback) and visit `http://acme.localhost:8000/api/v1/context/`.

## Tests (the permanent gates)

```bash
../nina/bin/pytest            # tenant isolation, authz, double-booking, TZ/DST
```

These suites are CI gates and must stay green forever:
- `apps/tenancy/tests/test_isolation.py` — data never crosses schemas.
- `apps/accounts/tests/test_authorization.py` — cross-tenant / escalation denied.
- `apps/booking/tests/test_double_booking.py` — incl. concurrent race.
- `apps/booking/tests/test_timezone.py` — DST correctness.

## Layout

```
config/            split settings, tenant + public URLconfs, celery, wsgi/asgi
apps/
  tenancy/         Business/Domain (public), provisioning, onboarding, operator
  accounts/        User + Membership (public), auth, authorization, permissions
  business/        per-tenant branding/vocabulary + the /context bootstrap
  booking/         services/staff/customers/hours, availability engine, bookings
  notifications/   channel abstraction, .ics, tenant-aware Celery tasks
  accounting/      flag-gated bookkeeping + idempotent auto-income
  bots/            per-tenant bots, scoped tools, pipeline, Telegram adapter
  audit/           per-tenant audit log
  common/          middleware, error envelope, pagination, health
```

API is versioned under `/api/v1`. OpenAPI at `/api/schema/`, Swagger at
`/api/docs/`. See `docs/ARCHITECTURE.md` and `docs/RUNBOOK.md`.
