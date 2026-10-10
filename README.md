# Tankly

Collaborative fuel and fleet tracking for farms and small businesses. Server-rendered FastAPI app with Jinja2 templates and PostgreSQL in production and local development. SQLite remains available for lightweight tests.

**Plan status:** Phases 0–22 complete (~402 tests). Next: [Stripe billing](.docs/STRIPE_BILLING.md) (Phase 23).

## Quick start

**Python 3.12** required (matches CI and Docker). Check with `python --version`.
Docker Desktop is required for the local PostgreSQL service.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
docker compose up -d db
python -m alembic upgrade head
python scripts/seed_dev.py
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Environment variables

Copy `.env.example` to `.env` (or `.env.beta.example` for Northflank). Key settings:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | local PostgreSQL URL | Application database; default local DB is `tankly_dev` |
| `TEST_DATABASE_URL` | local PostgreSQL URL | Dedicated test database; tests migrate and clear its tables, never point it at `tankly_dev` |
| `SECRET_KEY` | dev default | **Required** unique value when `ENV=production` |
| `ENV` | `development` | `production` for deploy |
| `BASE_URL` | `http://127.0.0.1:8000` | Canonical URL for local QR labels and password-reset links; use HTTPS in production |
| `REDIS_URL` | — | Required in production unless `SINGLE_WORKER_MODE=true` |
| `CRON_SECRET` | — | Required when `ENV=production`; cron uses `Authorization: Bearer …` |
| `REGISTRATION_INVITE_CODE` | — | Optional private-beta registration gate |
| `ALLOWED_HOSTS` | `*` | Comma-separated hostnames in production |
| `MAIL_*` | — | Brevo/SMTP for password reset and service reminders |
| `SENTRY_DSN` | — | Optional error tracking |
| `PLATFORM_ADMIN_EMAILS` | — | Comma-separated operator emails for `/platform` |

See `.env.example` for the full list.

## Dependencies

| File | Use |
|------|-----|
| `requirements-prod.txt` | Production runtime (Docker / deploy) |
| `requirements-dev.txt` | Local dev and CI (`pytest`, `ruff`, `httpx`, `pytest-cov`) |
| `requirements.txt` | Alias for `requirements-dev.txt` |

```powershell
pip install -r requirements-dev.txt   # local / CI
pip install -r requirements-prod.txt  # production image only
```

## Tests

```powershell
pytest
```

The test suite uses `TEST_DATABASE_URL` from `.env`, separate from the app's `DATABASE_URL`. It clears test tables and keeps the migrated test schema for reuse; never point it at `tankly_dev`.

With coverage:

```powershell
pytest --cov=app --cov-report=term-missing
```

Mirror CI (Postgres):

```powershell
$env:TEST_DATABASE_URL = "postgresql://tankly:tankly_local@localhost:5433/tankly_test"
pytest
```

Use a disposable test database; the suite applies migrations and clears its tables.

## Lint

```powershell
ruff check app tests
ruff format --check app tests
```

## Deploy

Production Docker image installs only `requirements-prod.txt` (no pytest/ruff).

Frontend vendor assets live in `app/static/vendor/` and are committed to git. Refresh after a version bump: `scripts/fetch-vendor.sh` (requires curl).

```powershell
docker build -t tankly .
```

| Guide | When |
|-------|------|
| [.docs/BETA_DEPLOY.md](.docs/BETA_DEPLOY.md) | Private beta on Northflank ($0) |
| [.docs/PRODUCTION.md](.docs/PRODUCTION.md) | Full production reference |

## Documentation

| Doc | Purpose |
|-----|---------|
| [.docs/DEVELOPMENT_PLAN.md](.docs/DEVELOPMENT_PLAN.md) | Phases 0–23, tests, acceptance criteria |
| [.docs/TECHNICAL_DOCUMENTATION.md](.docs/TECHNICAL_DOCUMENTATION.md) | Architecture, schema, routes |
| [.docs/DECISION_LOG.md](.docs/DECISION_LOG.md) | Design decisions (`D-XXX`) |
| [.docs/PLATFORM_ADMIN.md](.docs/PLATFORM_ADMIN.md) | Operator dashboard (Phase 22 — complete) |
| [.docs/STRIPE_BILLING.md](.docs/STRIPE_BILLING.md) | Stripe billing — **planned** (Phase 23) |
| [.docs/BETA_DEPLOY.md](.docs/BETA_DEPLOY.md) | Quick beta deploy |
| [.docs/PRODUCTION.md](.docs/PRODUCTION.md) | Production hardening & deploy |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | AI workflow — TDD, architecture, testing (canonical) |
| [.prompts/AGENT_PROMPT.md](.prompts/AGENT_PROMPT.md) | Phase kickoff prompt only (optional) |

## Project layout

```
app/                FastAPI application (routes, services, models, templates)
alembic/            Database migrations
tests/              pytest suite (~402 tests)
scripts/            start.sh, migrate.sh, fetch-vendor.sh, generate-beta-secrets.*
.docs/              Internal documentation
.github/            CI workflow + copilot-instructions.md
.cursor/rules/      Cursor always-on rules (→ copilot-instructions)
.prompts/           Phase kickoff agent prompt
```
