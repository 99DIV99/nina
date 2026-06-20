#!/usr/bin/env bash
# Idempotent release step: run AFTER `docker compose ... up -d`, once per deploy.
# Applies shared + tenant migrations, ensures the public tenant/domains exist,
# and collects static. Safe to re-run.
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

echo "==> migrate shared schema"
$COMPOSE run --rm web python manage.py migrate_schemas --shared

echo "==> bootstrap public tenant + domains"
# Pass your real apex hosts so non-tenant requests resolve to the public schema.
$COMPOSE run --rm web python manage.py bootstrap_public --hosts "${APEX_HOSTS:-yourdomain.com www.yourdomain.com}"

echo "==> migrate all tenant schemas"
$COMPOSE run --rm web python manage.py migrate_schemas

echo "==> collectstatic"
$COMPOSE run --rm web python manage.py collectstatic --noinput

# The running web process caches the hashed-static manifest at startup; reload it
# so freshly collected assets (e.g. admin) are found instead of 500-ing.
echo "==> reload web (refresh static manifest)"
$COMPOSE restart web

echo "==> release complete"
