#!/usr/bin/env bash
# Idempotent release step for the DEV stack: run AFTER
# `docker compose -f docker-compose.dev.yml ... up -d`, once per deploy.
# Applies shared + tenant migrations and ensures the public tenant/domains exist.
# No collectstatic: dev runs `runserver` (DEBUG=True) which serves static itself.
# Safe to re-run.
set -euo pipefail

COMPOSE="docker compose -f docker-compose.dev.yml --env-file .env.dev"

echo "==> migrate shared schema"
$COMPOSE run --rm web python manage.py migrate_schemas --shared

echo "==> bootstrap public tenant + domains (dev hosts)"
$COMPOSE run --rm web python manage.py bootstrap_public --hosts "${APEX_HOSTS:-dev.ninax.net www.dev.ninax.net}"

echo "==> migrate all tenant schemas"
$COMPOSE run --rm web python manage.py migrate_schemas

echo "==> dev release complete"
