# Architecture

## Multi-tenancy

`django-tenants` maps each request's hostname to a `Business` (tenant) and sets
the PostgreSQL `search_path` to that tenant's schema before any view runs
(`TenantMainMiddleware`, first in the stack). Tenant apps therefore never filter
by a business id — they physically cannot see another tenant's rows.

- **Public schema (SHARED_APPS):** `Business`, `Domain`, `User`, `Membership`,
  celery-beat. These must be cross-tenant, so they live once in `public`.
- **Tenant schema (TENANT_APPS):** `business`, `booking`, `notifications`,
  `accounting`, `bots`, `audit`. Cloned into every tenant schema at provisioning.

`btree_gist` is installed once in `public` (shared migration) so the booking
exclusion constraint resolves inside every tenant schema (public is always on the
search_path).

### Provisioning

`apps/tenancy/provisioning.create_business()` validates the subdomain (reserved
names blocked), creates the `Business` row — which auto-creates the schema and
runs tenant migrations — then the primary `Domain`, atomically.

## Authorization (the security spine)

The client is never trusted for identity. Every protected endpoint runs through
`apps/accounts/permissions.py`, which calls `current_membership(request)`:

```
host -> tenant (django-tenants)         # server-resolved
JWT/session -> user                     # server-resolved
Membership(user, tenant) -> role        # looked up, never sent by client
role -> permissions                     # static map, intersected with feature flags
```

A request body claiming `role`, `business_type`, or `has_records` is ignored. The
`/context` payload is an *outbound rendering hint* — it grants nothing.

## Booking correctness

- `Appointment` has a Postgres `ExclusionConstraint` on
  `(staff EQUAL, tstzrange(start_at, end_at) OVERLAPS)` for active statuses. Two
  overlapping active appointments for one staff member are impossible at the DB
  level, regardless of races. Under extreme contention Postgres may resolve the
  race as a deadlock; `create_appointment` retries the victim, then returns 409.
- The availability engine (`apps/booking/availability.py`) computes slots in the
  staff's local timezone and emits UTC, so DST transitions are handled correctly.
  It subtracts existing appointments (buffer-expanded) and time off, and honors
  lead time + max-advance.

## Bots

A bot lives in the tenant schema (so it belongs to exactly one tenant) and may
only call the scoped tools in `apps/bots/tools.py`, which all go through the
authorized booking service. Channels are pluggable adapters over one pipeline:
a web widget and a per-business Telegram bot ship today; WhatsApp/others slot in
the same way. Bot-created bookings are `pending` and require human review.

## Async

Celery tasks are tenant-aware: they receive the `schema_name` and run inside
`schema_context`, so a shared worker never touches the wrong schema. Reminders
fan out across all active tenants via celery-beat.
