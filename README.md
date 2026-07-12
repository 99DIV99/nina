# NINA Backend

**Multi-tenant booking and bookkeeping SaaS platform for service businesses.**

---

## What is NINA?

NINA is a **B2B SaaS platform** that enables service businesses (barbershops, salons, clinics, spas) to:
- Accept online bookings 24/7 via branded booking pages
- Manage appointments, staff schedules, and services
- Send automated SMS/email reminders to customers
- Track income, expenses, and generate business reports
- Integrate with Telegram and Bale bots for conversational booking

**Target market:** Iranian service businesses looking to digitize their booking operations.

---

## Key Features

### 📅 Booking Management
- **Public booking pages** - Customers book 24/7 without creating accounts
- **Real-time availability** - Automatic double-booking prevention
- **Staff & service management** - Define services, staff, working hours
- **Appointment lifecycle** - Book, confirm, complete, cancel, reschedule
- **Timezone-aware** - All calculations timezone and DST-correct

### 📱 Customer Communication
- **SMS notifications** - Confirmations, reminders via IranPayamak
- **Email notifications** - Booking confirmations and updates
- **OTP verification** - Secure phone-based authentication
- **Customizable messaging** - Business-specific vocabulary

### 💰 Bookkeeping & Accounting
- **Income/expense tracking** - Categorized financial records
- **Payment tracking** - Record appointment payments
- **Automated invoicing** - Generate invoices for paid appointments
- **Business reports** - Profit & loss, cash flow, staff performance
- **CSV export** - Download all reports

### 🤖 Integrations
- **Telegram bot** - Conversational booking via Telegram
- **Bale bot** - Iranian messaging platform integration
- **Async processing** - Celery-powered background tasks

---

## Technical Architecture

### Multi-Tenancy Model

**Schema-per-tenant isolation** using django-tenants:
- Each business gets its own PostgreSQL schema
- Each business gets its own subdomain (`salon.example.com`)
- Schema separation guarantees data isolation (no `business_id` columns needed)

```
PostgreSQL Database:
├── public schema (shared: users, roles, tenant info)
├── t_acme (Acme Salon - tenant schema)
│   ├── booking_appointment
│   ├── booking_staff
│   ├── accounting_income
│   └── ...
├── t_globe (Globe Spa - tenant schema)
│   └── ...
└── t_barber5 (Barber Shop #5)
    └── ...
```

### How Tenant Resolution Works

```
1. Request arrives: salon.example.com/api/v1/...
2. Middleware extracts subdomain → "salon"
3. System finds tenant → gets schema "t_salon"
4. Switch connection to schema "t_salon"
5. All queries now scoped to this tenant only
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.10 |
| **Framework** | Django 5.0 |
| **API** | Django REST Framework |
| **Database** | PostgreSQL 16 |
| **Multi-tenancy** | django-tenants (schema-per-tenant) |
| **Task Queue** | Celery with Redis broker |
| **Authentication** | JWT (SimpleJWT) |
| **SMS Provider** | IranPayamak |
| **API Docs** | drf-spectacular (OpenAPI 3.0) |
| **Testing** | pytest |
| **Deployment** | Docker, docker-compose |

---

## Project Structure

```
backend/
├── apps/
│   ├── accounts/        # Authentication, users, roles, permissions
│   ├── audit/           # Audit logging for admin actions
│   ├── booking/         # Appointments, services, staff, availability
│   ├── bots/            # Telegram/Bale bot integration
│   ├── business/        # Business branding, settings, vocabulary
│   ├── common/          # Shared utilities, exceptions, middleware
│   ├── notifications/   # SMS/email notifications, Celery tasks
│   ├── otp/             # OTP generation and verification
│   ├── tenancy/         # Tenant creation, subdomain management
│   └── accounting/      # Income, expenses, invoices, reports
├── config/              # Django settings, URLs, Celery config
├── deploy/              # Deployment scripts
└── docs/                # Architecture documentation
```

---

## Core Design Principles

1. **Schema is the isolation boundary** - Tenant tables carry no `business_id`; schema separation enforces isolation
2. **Server-side authorization is absolute** - Client claims ignored; permissions derived from `Membership(user, tenant)` every request
3. **Booking correctness is non-negotiable** - Double-booking prevented by Postgres exclusion constraints and atomic transactions
4. **Feature flags drive capability** - Business type and feature flags determine functionality, not schema changes
5. **Bots are actors, not backdoors** - Bots book through same authorized services as humans

---

## Getting Started

### Prerequisites

```bash
- Python 3.10+
- PostgreSQL 14+
- Redis (for Celery)
- Docker (optional, for local DB/Redis)
```

### Installation

```bash
# Clone repository
git clone https://github.com/your-org/nina-backend.git
cd nina-backend

# Create virtual environment
python3.10 -m venv ../nina
source ../nina/bin/activate

# Install dependencies
pip install -r requirements/dev.txt

# Setup environment
cp .env.example .env
# Edit .env with your configuration

# Start database (with Docker)
docker compose up -d db redis

# Run migrations
make migrate-shared      # Public schema migrations
make migrate-tenants     # Tenant schema migrations

# Create demo tenant
python manage.py seed_demo

# Run development server
make run
# Server running at http://localhost:8000
```

### Access Demo Tenant

Add to `/etc/hosts`:
```
127.0.0.1 acme.localhost
```

Visit: `http://acme.localhost:8000/api/v1/context/`

---

## Testing

```bash
# Run all tests
pytest

# Run specific module tests
pytest apps/booking/tests/
pytest apps/accounting/tests/

# Run with coverage
pytest --cov=apps --cov-report=html
```

**Key test suites:**
- Tenant isolation (cross-tenant data leakage prevention)
- Authorization (permission enforcement)
- Double-booking prevention (including race conditions)
- Timezone and DST handling
- OTP functionality
- Accounting calculations

---

## Deployment

### Production Architecture

```
Nginx (reverse proxy, SSL termination)
  ↓
Gunicorn (Django application server)
  ↓
PostgreSQL (database)
Redis (Celery broker and backend)
Celery workers (background task processing)
Celery beat (scheduled task execution)
```

### Deployment Commands

```bash
# Build and start production services
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# Run database migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Collect static files
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

### Environment Configuration

Required production environment variables:
```
DJANGO_SETTINGS_MODULE=config.settings.prod
POSTGRES_HOST=db
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
IRANPAYAMAK_API_KEY=your_api_key
IRANPAYAMAK_PATTERN_BOOKING=your_pattern_code
SECRET_KEY=your_django_secret_key
```

---

## API Documentation

OpenAPI/Swagger documentation:
- Development: `http://localhost:8000/api/docs/`
- Production: `https://api.example.com/api/docs/`

### Example Endpoints

| Purpose | Endpoint | Method |
|---------|----------|--------|
| Public booking | `/api/v1/public-booking/book` | POST |
| Business branding | `/api/v1/public-booking/business` | GET |
| OTP login | `/api/v1/auth/login/otp/verify` | POST |
| Profit & Loss | `/api/v1/accounting/reports/pnl` | GET |
| Staff performance | `/api/v1/accounting/reports/staff` | GET |

---

## Development Workflow

### Branch Strategy

- `main` - Production branch (auto-deploys to production)
- `dev` - Development branch (auto-deploys to dev environment)

### Making Changes

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and test
pytest

# Format code
black apps/
isort apps/

# Commit and push
git add .
git commit -m "Description of changes"
git push origin feature/your-feature-name
```

### Code Quality

- **Type hints** - Used throughout for IDE support
- **Docstrings** - Google-style documentation
- **Testing** - Comprehensive test coverage
- **Linting** - Black and isort for consistent formatting

---

## Security Features

- **Multi-tenant isolation** - Schema-per-tenant prevents cross-tenant data access
- **Server-side authorization** - Permission checks on every request
- **OTP verification** - Phone-based authentication for sensitive actions
- **Rate limiting** - Throttling on public endpoints
- **SQL injection protection** - Django ORM parameterized queries
- **CSRF protection** - Enabled where appropriate

---

## Performance Optimizations

- **Database indexing** - Optimized queries with proper indexes
- **Query optimization** - select_related/prefetch for N+1 prevention
- **Connection pooling** - Efficient database connections
- **Async processing** - Celery for background tasks

---

## Monitoring & Logging

- **Audit logging** - Admin actions tracked in audit app
- **Structured logging** - JSON logs for debugging
- **Celery monitoring** - Task execution tracking
- **Health checks** - `/healthz` and `/readyz` endpoints

---

## Business Logic Highlights

### Double-Booking Prevention
Uses PostgreSQL exclusion constraints to prevent concurrent bookings of the same slot:

```python
# apps/booking/models.py
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["staff", "start_at"],
            condition=Q(status__in=ACTIVE_STATUSES),
            name="no_double_booking",
        )
    ]
```

### Auto-Income Generation
When appointments are marked as paid and completed, accounting income is automatically created:

```python
# apps/accounting/signals.py
@receiver(appointment_completed)
def on_appointment_completed(sender, appointment, **kwargs):
    record_income_for_appointment(appointment)
```

### Timezone Handling
All appointment times stored in business timezone, with proper DST transitions handled.

---


## Contact

- **Website:** https://ninax.net
- **Documentation:** See `docs/` directory
