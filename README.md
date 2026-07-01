# Tankly

Collaborative fuel and fleet tracking for farms and small businesses. Server-rendered FastAPI app with Jinja2 templates, PostgreSQL (production), and SQLite (local dev).

## Quick start

**Python 3.12** required (matches CI and Docker). Download from [python.org](https://www.python.org/downloads/) if needed. Check with `python --version`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Environment variables

Copy `.env.example` to `.env`. Key settings:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `sqlite:///./dev.db` | Use Postgres in production |
| `SECRET_KEY` | dev default | **Required** unique value when `ENV=production` |
| `ENV` | `development` | Set to `production` for deploy |
| `BASE_URL` | — | Public URL for password-reset links |
| `REDIS_URL` | — | Required in production unless `SINGLE_WORKER_MODE=true` |
| `CRON_SECRET` | — | Required when `ENV=production` |
| `ALLOWED_HOSTS` | `*` | Comma-separated hostnames in production |
| `MAIL_*` | — | SMTP for password reset and service reminders |
| `SENTRY_DSN` | — | Optional error tracking |

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

With coverage:

```powershell
pytest --cov=app --cov-report=term-missing
```

Mirror CI (Postgres):

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/tankapp_test"
pytest
```

## Lint

```powershell
ruff check app tests
ruff format --check app tests
```

## Deploy

Production Docker image installs only `requirements-prod.txt` (no pytest/ruff).

Frontend vendor assets live in `app/static/vendor/` and are committed to git. To refresh them after a version bump, run `scripts/fetch-vendor.sh` (requires curl).

```powershell
docker build -t tankapp .
```

Full beta deployment guide: [.docs/PRODUCTION.md](.docs/PRODUCTION.md)

## Documentation

| Doc | Purpose |
|-----|---------|
| [.docs/PRODUCTION.md](.docs/PRODUCTION.md) | Deploy, env vars, security checklist |
| [.docs/TECHNICAL_DOCUMENTATION.md](.docs/TECHNICAL_DOCUMENTATION.md) | Architecture, schema, routes |
| [.docs/DEVELOPMENT_PLAN.md](.docs/DEVELOPMENT_PLAN.md) | Feature phases and test plan |
| [.docs/DECISION_LOG.md](.docs/DECISION_LOG.md) | Design decisions |

## Project layout

```
app/           FastAPI application (routes, services, models, templates)
alembic/       Database migrations
tests/         pytest suite
scripts/       start.sh, migrate.sh, fetch-vendor.sh
.docs/         Internal documentation
```
