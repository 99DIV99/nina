# NINA — VPS Deployment & CI/CD Runbook

This describes deploying the **backend** (Django + Celery), the **frontend**
(Next.js), and the **bots** (which live *inside* the backend) to a single VPS
with Docker Compose, fronted by host **nginx**. CI/CD runs on GitHub Actions and
deploys over SSH on push to `main`.

> **Where the bot runs:** there is no separate bot process. The bot's HTTP entry
> points (web-chat widget + Telegram webhook) are served by the backend `web`
> container, and the conversation pipeline runs in the Celery `worker`. So
> "deploy the bot" = deploy the backend correctly **and** give each tenant a
> valid HTTPS subdomain (Telegram only registers webhooks over valid TLS). The
> web-chat widget works without TLS; Telegram does not.

---

## 0. Architecture on the box

```
                       Internet
                          │  :80 (:443 later)
                    ┌─────▼─────┐
                    │   nginx   │   server_name yourdomain.com *.yourdomain.com
                    └──┬─────┬──┘
        /api /admin /static │     │  everything else
        /healthz  webhooks  │     │
                 ┌──────────▼┐   ┌▼────────────┐
                 │ backend   │   │  frontend   │
                 │ web :8000 │   │ next :3000  │   (both bound to 127.0.0.1)
                 └─┬───┬───┬─┘   └─────────────┘
          worker ──┘   │   └── beat            frontend calls backend via
                   ┌───▼───┐ ┌───────┐         http(s)://{tenant}.yourdomain
                   │postgres│ │ redis │         so the Host header carries
                   └────────┘ └───────┘         the tenant (schema routing).
```

**Tenant resolution is by Host header.** Both nginx and the Next.js middleware
read the host. Never put the API on a separate `api.` hostname — the backend
would then resolve to the public schema and tenants would break.

---

## 1. DNS (required now, even without wildcard TLS)

Create two A records pointing at the VPS IP:

| Type | Name              | Value        |
|------|-------------------|--------------|
| A    | `yourdomain.com`  | `VPS_IP`     |
| A    | `*.yourdomain.com`| `VPS_IP`     |

The wildcard A record lets every tenant subdomain resolve. (Wildcard **TLS** is
a separate step — see §7.)

---

## 2. Provision the VPS

```bash
# As root on Ubuntu 22.04+
apt-get update && apt-get install -y nginx git ufw
curl -fsSL https://get.docker.com | sh           # Docker Engine + compose plugin

ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw --force enable

# A non-root deploy user that can run docker and owns the app dir
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
mkdir -p /opt/nina && chown deploy:deploy /opt/nina
```

Add your CI SSH **public** key to `/home/deploy/.ssh/authorized_keys` (see §6).

---

## 3. Get the code onto the box

Two separate repos, side by side:

```bash
sudo -iu deploy
cd /opt/nina
git clone git@github.com:YOURORG/nina-backend.git  backend
git clone git@github.com:YOURORG/nina-frontend.git frontend
```

---

## 4. Backend bring-up

```bash
cd /opt/nina/backend
cp .env.prod.example .env.prod
# Edit .env.prod:
#   DJANGO_SECRET_KEY  -> python -c "import secrets; print(secrets.token_urlsafe(64))"
#   BASE_DOMAIN, DJANGO_ALLOWED_HOSTS  -> your domain (note the leading-dot wildcard host)
#   POSTGRES_PASSWORD  -> a strong password
#   DJANGO_SETTINGS_MODULE stays config.settings.staging for the HTTP-first bring-up

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
APEX_HOSTS="yourdomain.com www.yourdomain.com" bash deploy/release.sh
```

`release.sh` is idempotent and runs the **permanent migration order**:
`migrate_schemas --shared` → `bootstrap_public` → `migrate_schemas` →
`collectstatic`. Re-run it after every deploy (CI does this for you).

Create an operator/superuser and a first tenant:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm web \
  python manage.py createsuperuser
# Seed a demo tenant (optional, see apps/tenancy/management/commands/seed_demo.py)
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm web \
  python manage.py seed_demo
```

---

## 5. Frontend bring-up

```bash
cd /opt/nina/frontend
cp .env.prod.example .env.prod
# Edit .env.prod:
#   NINA_BASE_DOMAIN=yourdomain.com
#   NINA_API_PROTO=http  NINA_API_PORT=80         (switch to https/443 after TLS)
#   NINA_COOKIE_SECURE=false                       (remove once TLS is live)

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

### nginx

```bash
sudo cp /opt/nina/backend/deploy/nginx/nina.conf /etc/nginx/sites-available/nina
sudo sed -i 's/yourdomain.com/REALDOMAIN.com/g' /etc/nginx/sites-available/nina
sudo ln -sf /etc/nginx/sites-available/nina /etc/nginx/sites-enabled/nina
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Smoke test:

```bash
curl -s http://yourdomain.com/healthz          # backend health via nginx
curl -sI http://acme.yourdomain.com/            # tenant host -> frontend
```

---

## 6. CI/CD (GitHub Actions)

Each repo carries two workflows in `.github/workflows/`:

- `ci.yml` — runs on every push & PR.
  - **backend:** ruff + black/isort check + pytest (against a Postgres + Redis service). The permanent **tenant-isolation** and **authorization** suites run here.
  - **frontend:** `tsc --noEmit` + `next lint` + `next build`.
- `deploy.yml` — runs **only after `*-ci` succeeds on `main`**, then SSHes to the VPS, pulls, rebuilds, and (backend) re-runs `release.sh`.

### Required repo secrets (Settings → Secrets → Actions)

Set these in **both** repos:

| Secret          | Example / meaning                                   |
|-----------------|-----------------------------------------------------|
| `VPS_HOST`      | `203.0.113.10`                                       |
| `VPS_USER`      | `deploy`                                             |
| `VPS_SSH_KEY`   | the **private** key whose public half is in `authorized_keys` |
| `VPS_SSH_PORT`  | optional, defaults to `22`                           |

Backend repo also needs:

| Secret         | Example                                  |
|----------------|------------------------------------------|
| `BACKEND_DIR`  | `/opt/nina/backend`                      |
| `APEX_HOSTS`   | `yourdomain.com www.yourdomain.com`      |

Frontend repo also needs:

| Secret          | Example                |
|-----------------|------------------------|
| `FRONTEND_DIR`  | `/opt/nina/frontend`   |

Generate the deploy key once:

```bash
ssh-keygen -t ed25519 -C "nina-ci" -f nina_ci -N ""
# nina_ci.pub  -> /home/deploy/.ssh/authorized_keys on the VPS
# nina_ci      -> paste into the VPS_SSH_KEY secret in BOTH repos
```

Then: push to `main` → CI runs → on green, the box pulls and restarts.

---

## 7. Going live: wildcard TLS (required before Telegram bots & real tenants)

The bring-up above is HTTP-only. Before onboarding real businesses (and for
Telegram webhooks at all), issue a **wildcard cert** via DNS-01 and flip the
stack to HTTPS:

```bash
sudo apt-get install -y certbot python3-certbot-dns-<provider>
sudo certbot certonly --dns-<provider> \
  -d yourdomain.com -d '*.yourdomain.com'
# cert: /etc/letsencrypt/live/yourdomain.com/{fullchain,privkey}.pem
```

Then:

1. Add a `listen 443 ssl;` server block to `nina.conf` pointing at the cert,
   keeping the same location routing; redirect `:80` → `:443`.
2. Backend `.env.prod`: set `DJANGO_SETTINGS_MODULE=config.settings.prod`
   (enables HSTS + SSL redirect + secure cookies).
3. Frontend `.env.prod`: `NINA_API_PROTO=https`, `NINA_API_PORT=443`, and
   **remove** `NINA_COOKIE_SECURE=false`.
4. `docker compose ... up -d` both stacks, `sudo systemctl reload nginx`.
5. Auto-renew: `certbot renew` runs from the packaged systemd timer; add an
   nginx reload hook.

### Per-tenant Telegram bot

Once a tenant has valid HTTPS, the business enables a bot in the panel (or via
`POST /api/v1/bots/.../enable-telegram` with its BotFather token). The backend
registers the webhook at `https://{tenant}.yourdomain.com/api/v1/bots/telegram/webhook`,
verified by a per-bot secret. No infra change is needed per tenant — the wildcard
cert + wildcard DNS already cover every subdomain.

---

## 8. Operations cheatsheet

```bash
# logs
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f web worker beat

# run a management command
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm web python manage.py <cmd>

# DB backup (per the B10 backup runbook)
docker compose -f docker-compose.prod.yml --env-file .env.prod exec db \
  pg_dump -U nina nina | gzip > /opt/nina/backups/nina-$(date +%F).sql.gz

# restart after a manual change
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Reminders run via Celery **beat** → register the `dispatch_due_reminders`
periodic task in the django-celery-beat schedule (admin UI or a data migration);
the worker executes it.
