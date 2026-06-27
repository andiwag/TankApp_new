# TankApp – Production & Beta Deployment Guide

This document covers **production hardening** and **step-by-step deployment** for TankApp.

**Chosen beta path (this guide):** $0/month on [Northflank Sandbox](https://northflank.com/pricing) for personal testing and 1–2 beta farms.

**Quick start:** see [BETA_DEPLOY.md](./BETA_DEPLOY.md) for a focused private-beta checklist.

| Component | Service | Cost |
|-----------|---------|------|
| Web app | Northflank Sandbox (combined service) | $0 |
| Database | Northflank Sandbox (PostgreSQL addon) | $0 |
| Email (optional) | [Brevo](https://www.brevo.com) free SMTP | $0 |
| Domain | Northflank `*.code.run` subdomain (free SSL) | $0 |

**Why Northflank Sandbox (vs Render + Neon):**

- **No cold starts** — always-on compute on the free Sandbox tier
- **App + Postgres in one dashboard** — `DATABASE_URL` linked via secret group or env vars
- **No 30-day database expiry** (unlike Render's free Postgres)
- **Git push deploy** — buildpack or Dockerfile, HTTPS included

**Beta trade-offs:**

- Credit card required for identity verification (Sandbox itself is $0; configure billing alerts)
- Northflank labels Sandbox **"not for production"** — appropriate for beta, not paying customers
- Modest sandbox resources (~256–512 MB RAM per service)
- Smaller community than Render; fewer copy-paste FastAPI tutorials

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Pre-deploy checklist (code changes)](#2-pre-deploy-checklist-code-changes)
3. [Production hardening](#3-production-hardening)
4. [Deploy on Northflank Sandbox](#4-deploy-on-northflank-sandbox)
5. [Optional: password reset email (Brevo)](#5-optional-password-reset-email-brevo)
6. [Post-deploy verification](#6-post-deploy-verification)
7. [Operating the beta](#7-operating-the-beta)
8. [Upgrading off the free tier](#8-upgrading-off-the-free-tier)
9. [Alternative paths (reference)](#9-alternative-paths-reference)

---

## 1. Architecture overview

```
Browser (HTTPS)
      ↓
Northflank combined service  ──→  uvicorn (FastAPI + Jinja2 templates)
      ↓                              ↑ alembic upgrade head (on container start)
Northflank Postgres addon    ←──  SQLAlchemy + Alembic migrations
      ↓
Brevo SMTP (opt.)            ←──  password reset emails
```

TankApp is **server-rendered** (not a SPA). No frontend build step. Tailwind CSS and Alpine.js load from CDN.

**Do not use SQLite on Northflank.** Container filesystems are ephemeral; data would be lost on redeploy. Always use the Postgres addon.

---

## 2. Pre-deploy checklist (code changes)

Complete these **before** the first deploy.

### Required

- [x] **Add a PostgreSQL driver** to `requirements.txt`:
  ```
  psycopg2-binary==2.9.10
  ```

- [x] **Add a `Dockerfile`** (recommended — Northflank's official FastAPI guide uses Docker). See [§4.2](#42-add-dockerfile-and-start-script) for a copy-paste example.

- [ ] **Generate a strong `SECRET_KEY`** (never use the dev default):
  ```powershell
  .\scripts\generate-beta-secrets.ps1
  ```

- [x] **Add `.venv/` to `.gitignore`** (alongside existing `venv/`).

### Recommended before sharing with beta farms

- [x] **Session cookie `Secure` flag** — implemented in `app/auth.py` (`secure=settings.is_production`).

- [x] **Flash cookie `Secure` flag** — `app/flash.py` `set_flash()` sets `secure=settings.is_production`.

- [x] **Password reset email** — `app/routes/auth.py` sends via `fastapi-mail` when `MAIL_*` and `BASE_URL` are set.

- [x] **PWA test** — accepts `text/javascript` for service worker content type.

- [x] **Private beta registration gate** — set `REGISTRATION_INVITE_CODE` (see [BETA_DEPLOY.md](./BETA_DEPLOY.md)).

- [x] **Graceful error pages** — unhandled errors show friendly HTML/JSON instead of raw tracebacks.

### Buildpack alternative (no Docker)

If you prefer buildpacks instead of a Dockerfile:

- [ ] Add `runtime.txt` with `python-3.12.8` (do not use Python 3.14 locally — buildpacks may not support it yet).
- [ ] Add a `Procfile`:
  ```
  web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
  release: alembic upgrade head
  ```
  Northflank injects `PORT` automatically. Run migrations via a one-off **Job** or a startup script — buildpacks do not have Render's built-in release command.

### Not required for beta (documented limitations)

| Item | Beta impact | Fix when |
|------|-------------|----------|
| In-memory rate limiting (no `REDIS_URL`) | Resets on redeploy; not shared across workers | Set `REDIS_URL` on Northflank (Redis addon or Upstash) |
| `subscription_tier` | Unused column | When billing is added |

**Implemented since this guide was first written:** server-side session revocation (profile → active sessions), audit log UI (`/settings/audit`), maintenance logs + service reminders, CSV export, analytics, and Redis-backed rate limiting when `REDIS_URL` is set.

---

## 3. Production hardening

### 3.1 Environment variables

Set these on your Northflank service (**Environment** page). Never commit real values to git.

| Variable | Example / notes | Required |
|----------|-----------------|----------|
| `DATABASE_URL` | From Postgres addon `POSTGRES_URI` (see [§4.4](#44-link-postgres-to-the-app)) | Yes |
| `SECRET_KEY` | Random 32+ byte string | Yes |
| `ENV` | `production` | Yes |
| `SESSION_COOKIE_NAME` | `tankapp_session` (default OK) | No |
| `MAIL_USERNAME` | Brevo SMTP login | For email |
| `MAIL_PASSWORD` | Brevo SMTP key | For email |
| `MAIL_FROM` | `noreply@yourdomain.com` | For email |
| `MAIL_SERVER` | `smtp-relay.brevo.com` | For email |
| `MAIL_PORT` | `587` | For email |
| `MAIL_STARTTLS` | `true` | For email |
| `BASE_URL` | `https://your-app.code.run` | For password-reset and reminder email links |
| `REDIS_URL` | Redis connection string | **Yes** in production (or set `SINGLE_WORKER_MODE=true` for one worker) |
| `CRON_SECRET` | Random secret for scheduled jobs | **Yes** when `ENV=production` |
| `ALLOWED_HOSTS` | `your-app.code.run` (comma-separated) | Recommended in production |
| `SENTRY_DSN` | Sentry project DSN | Optional error tracking |
| `RUN_MIGRATIONS_ON_START` | `true` (default) or `false` | Set `false` for multi-replica; run `scripts/migrate.sh` as a Job |
| `SINGLE_WORKER_MODE` | `true` only for single-worker beta | Allows in-memory rate limits without Redis |

Copy `.env.example` as a local reference; production values live only on Northflank.

### 3.2 `DATABASE_URL` format

Northflank provides `POSTGRES_URI` in the format `postgresql://user:pass@host:port/database`. Map this to `DATABASE_URL` for TankApp (which reads `DATABASE_URL` in `app/config.py`).

If you copy a connection string from elsewhere that uses `postgres://`, change the prefix to `postgresql://` for SQLAlchemy 2.x.

### 3.3 Security checklist

| Control | Status in codebase | Production action |
|---------|-------------------|-------------------|
| Password hashing (bcrypt) | Implemented | None |
| CSRF on all POST routes | Implemented | Set `ENV=production` (enables secure CSRF cookie) |
| Session cookie HttpOnly | Implemented | None |
| Session cookie Secure | Implemented (`secure=settings.is_production`) | Set `ENV=production` |
| Session cookie SameSite | `lax` | OK for SSR forms |
| Session revocation | Server-side `UserSession` rows | Users can revoke sessions on profile page |
| Group-scoped queries + membership checks | Implemented | None |
| Soft deletes | Implemented | None |
| Rate limiting (login/register/reset) | Redis or in-memory (`SINGLE_WORKER_MODE`) | Set `REDIS_URL` for multi-worker |
| Security headers (CSP, X-Frame-Options, etc.) | Implemented | None |
| Host header validation | `ALLOWED_HOSTS` | Set to your Northflank hostname |
| Password reset anti-enumeration | Implemented | None |
| HTTPS | Northflank provides automatically | None |
| Secrets in repo | `.env` gitignored | Verify before push |

### 3.4 Logging and error tracking

- **Development:** human-readable logs to stdout.
- **Production:** JSON-structured logs to stdout (Northflank **Observe** tab).
- **Optional:** set `SENTRY_DSN` to send unhandled exceptions to [Sentry](https://sentry.io).

### 3.5 Backups

Northflank Postgres addons support backup schedules (configure when creating the addon or on the addon settings page). For beta farms with real data:

1. Enable a backup schedule on the Postgres addon.
2. Before risky schema changes, fork the addon or take a manual backup.
3. Export critical data periodically if farms depend on it.

### 3.6 Health checks

| Endpoint | Purpose | Expected |
|----------|---------|----------|
| `GET /health` | Liveness — process is running | `200 {"status":"ok"}` |
| `GET /health/ready` | Readiness — database accepts queries | `200 {"status":"ready"}` or `503` |

Point Northflank **liveness** at `/health` and **readiness** at `/health/ready` when both are supported.

### 3.7 Database migrations (multi-replica)

For a **single** Sandbox service, `scripts/start.sh` runs `alembic upgrade head` on boot (default).

For **multiple replicas**, set `RUN_MIGRATIONS_ON_START=false` on the web service and run migrations once per deploy:

```sh
scripts/migrate.sh
```

Use a Northflank **Job** (or manual one-off container) with the same image and `DATABASE_URL` before scaling the web service.

### 3.8 Service reminder cron

Maintenance service reminders are sent by a **POST** endpoint (CSRF-exempt). Schedule it daily via a Northflank **Cron Job** or external scheduler (e.g. cron-job.org):

```
POST https://your-app.code.run/cron/service-reminders
Authorization: Bearer <CRON_SECRET>
```

Requirements:

- `CRON_SECRET` set on the web service (same value in the cron job headers)
- Mail env vars configured (`MAIL_*` and `BASE_URL`)
- Migrations applied (`maintenance_logs.reminder_sent_at` column exists)

The job claims each due log atomically so concurrent runs do not duplicate emails. If every admin email fails for a log, the claim is released so the next run retries.

---

## 4. Deploy on Northflank Sandbox

### 4.1 Create account and project

1. Sign up at [northflank.com](https://northflank.com).
2. Add a payment method when prompted (identity verification — Sandbox usage is $0; set billing alerts under **Billing**).
3. Create a **team** (or use your personal team).
4. Create a **project** named `tankapp-beta`.
5. Connect your **GitHub** account and grant access to the `TankApp_new` repository.

**Sandbox limits (free forever):**

| Resource | Limit |
|----------|-------|
| Services | 2 (always-on, no sleeping) |
| Postgres addons | 1 |
| Cron jobs | 2 |
| Credit card | Required for verification |

---

### 4.2 Add Dockerfile and start script

Recommended approach: run migrations on container start, then start uvicorn.

**`Dockerfile`** (project root):

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

COPY scripts/start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
```

**`scripts/start.sh`**:

```bash
#!/bin/sh
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Northflank injects `PORT` at runtime — the start script uses it automatically.

Commit and push these files before creating the service.

---

### 4.3 Create PostgreSQL addon

1. In your project: **Create new → Addon → PostgreSQL**.
2. Name: `tankapp-db`.
3. Version: default (16+ is fine).
4. **Networking:** keep internal (not publicly accessible) — the app connects within the same project.
5. **Resources:** Sandbox defaults are sufficient for beta.
6. **Optional:** set custom database name to `tankapp` if you prefer (cannot change later).
7. **Optional:** add a backup schedule.
8. Click **Create addon** and wait until status is running.

Note the connection details on the addon's **Connection details** page — you will need `POSTGRES_URI`.

---

### 4.4 Link Postgres to the app

**Option A — Secret group (recommended):**

1. **Create new → Secret group** in your project.
2. Link the `tankapp-db` addon.
3. Select `POSTGRES_URI` and set alias **`DATABASE_URL`**.
4. Enable **Apply secrets to specific services** and select your web service (after creating it in §4.5).

**Option B — Manual env var:**

1. Copy `POSTGRES_URI` from the addon connection details.
2. On your service **Environment** page, add:
   ```
   DATABASE_URL=<POSTGRES_URI value>
   ```

---

### 4.5 Create combined service (web app)

A **combined service** builds from Git and deploys in one step — simplest for beta.

1. **Create new → Service → Combined service**.
2. Name: `tankapp-web`.
3. **Repository:** select `TankApp_new`, branch `main`.
4. **Build type:** `Dockerfile` (path: `/Dockerfile`, context: repo root).
5. **Networking:** Northflank auto-detects port 8000 from `EXPOSE`. Confirm public HTTP is enabled — you get a `*.code.run` URL with free TLS.
6. **Environment variables** (if not using secret group for all):
   ```
   SECRET_KEY=<generated secret>
   ENV=production
   ```
7. **Health check:** path `/health`, port matches your exposed port.
8. Link the secret group from §4.4 if using Option A.
9. Click **Create service**.

Northflank builds the Docker image, runs the container, and provides a public HTTPS URL like:

```
https://tankapp-web-<hash>.code.run
```

### 4.6 Verify first deploy

1. Open the service **Logs** tab.
2. Confirm `alembic upgrade head` runs without errors.
3. Confirm uvicorn starts and listens on the injected port.
4. Open the public URL → you should see the login page.

**Auto-deploy:** enabled by default — pushes to `main` trigger rebuild and redeploy.

---

### 4.7 Optional: migration job instead of startup script

If you prefer migrations separate from app startup (e.g. multiple replicas later):

1. **Create new → Job** (uses one of your 2 free Sandbox jobs).
2. Same repo + Dockerfile, but override command:
   ```
   alembic upgrade head
   ```
3. Run the job manually before each deploy that includes new migrations.

For a single-instance beta, the startup script in §4.2 is simpler.

---

## 5. Optional: password reset email (Brevo)

Password reset currently **logs links in development** and does **nothing in production** until `_deliver_reset_token()` is implemented.

### For beta without email

Tell beta users you will reset passwords manually, or share accounts only you control during testing.

### For beta with email (recommended if farms use forgot-password)

1. Sign up at [brevo.com](https://www.brevo.com) (free tier: ~300 emails/day).
2. Create an SMTP key: **SMTP & API → SMTP**.
3. Add Northflank environment variables:

```
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_STARTTLS=true
MAIL_USERNAME=<your Brevo login email>
MAIL_PASSWORD=<Brevo SMTP key>
MAIL_FROM=noreply@yourdomain.com
```

4. Password reset uses `fastapi-mail` (`app/mail.py`). Set `BASE_URL` to your public Northflank URL so reset links resolve correctly:

```
https://tankapp-web-<hash>.code.run
```

---

## 6. Post-deploy verification

### Automated CI (GitHub Actions)

Pushes and pull requests to `main` run `.github/workflows/ci.yml`:

1. **Lint** — `ruff check` and `ruff format --check` on `app/` and `tests/`.
2. **Test** — full `pytest` on **Postgres 16** (migrations via Alembic, then all tests).

Local default remains SQLite in-memory when `DATABASE_URL` is unset. To mirror CI locally with Docker:

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/tankapp_test"
pytest
```

### Automated (local, before each deploy)

```powershell
.\.venv\Scripts\Activate.ps1
pytest
```

All tests should pass locally before pushing.

### Manual (on the live URL)

- [ ] `GET /health` returns `{"status":"ok"}`
- [ ] `GET /health/ready` returns `{"status":"ready"}`
- [ ] `GET /login` loads with Tailwind styling
- [ ] Register a new account
- [ ] Create a group; note the invite code
- [ ] Add a vehicle and a fuel entry
- [ ] Dashboard and summary show correct numbers
- [ ] Log out and log back in
- [ ] Open `/static/manifest.json` (PWA)
- [ ] Second browser/incognito: join group via invite code
- [ ] Forgot-password flow (if email is configured)
- [ ] Maintenance log + dashboard service reminders widget
- [ ] `POST /cron/service-reminders` with Bearer token (if reminders enabled)

### Responsiveness test (Sandbox advantage)

Unlike Render's free tier, Northflank Sandbox does **not** spin down after idle time. After 20+ minutes without visits, the login page should still load immediately — no 30–60 second cold start.

---

## 7. Operating the beta

### Sharing with 1–2 farms

1. Send them the Northflank URL (`https://….code.run`).
2. Each farm admin **registers** and **creates a group**.
3. Share invite codes (`FARM-XXXXX`) with their workers.
4. Suggest **contributor** role for workers who log fuel; **reader** for view-only.

### Redeploying after code changes

1. Push to GitHub `main`.
2. Northflank auto-builds and redeploys (if CI is enabled on the service).
3. `alembic upgrade head` runs on container start via `scripts/start.sh`.
4. Check service **Logs** for errors.

### Monitoring

- **Northflank service logs** — runtime errors, migration output, uvicorn access logs.
- **Addon metrics** — Postgres storage and connection health on the addon **Observe** page.
- No APM needed for beta.

### If something breaks

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Build fails | Missing `psycopg2-binary` or Dockerfile error | Check build logs; fix `requirements.txt` |
| DB connection error | `DATABASE_URL` not set or wrong | Check secret group link or env var |
| `ModuleNotFoundError: psycopg2` | Driver not in requirements | Add `psycopg2-binary` |
| Migrations fail | DB not ready / wrong URL | Verify addon is running; check `postgresql://` prefix |
| CSRF errors | Cookie mismatch HTTP/HTTPS | Ensure `ENV=production` |
| 502 after deploy | App not listening on `PORT` | Use `$PORT` in start script, not hardcoded 8000 |
| Password reset does nothing | Email not implemented | See [§5](#5-optional-password-reset-email-brevo) |
| Unexpected charge | Exceeded Sandbox limits | Check billing; stay on Sandbox plan |

---

## 8. Upgrading off the free tier

When beta farms depend on the app daily or you need production SLAs:

| Step | Change | Cost | Benefit |
|------|--------|------|---------|
| 1 | Northflank **Pay-as-you-go** | ~$5–25/mo per service | Production SLA, more CPU/RAM |
| 2 | Custom domain | ~$10/yr | Professional URL (free SSL on Northflank) |
| 3 | Redis addon or Upstash | ~$0–5/mo | Shared rate limits across replicas |
| 4 | **Railway Hobby** (migrate) | ~$5/mo | Alternative if you want simpler billing |
| 5 | **Hetzner VPS + Docker** | ~€4/mo | Cheapest long-term if you accept ops |

**Northflank Pay-as-you-go** is the natural upgrade — same platform, more resources, no migration.

---

## 9. Alternative paths (reference)

| Path | Cost | Cold starts | Ops | Best for |
|------|------|-------------|-----|----------|
| **Northflank Sandbox** (this guide) | $0 | **None** | Low | Beta with 1–2 farms |
| **Render + Neon** | $0 | 30–60s (Render) | Medium (2 vendors) | No credit card available |
| **Koyeb + Neon** | $0 | 1–5s after 1 hr idle | Medium | Faster cold starts than Render |
| **Railway Hobby** | ~$5/mo | None | Low | First paid step |
| **Render Starter + Neon** | ~$7/mo | None | Low–medium | Always-on without Northflank |
| **Hetzner VPS + Docker** | ~€4/mo | None | High | Long-term cost optimization |
| **Oracle Cloud free VM** | $0 | None | Very high | Maximum free, maximum pain |

### Render + Neon (no-credit-card fallback)

If you cannot add a card to Northflank, use the previous split-stack approach:

1. **Neon** free Postgres (permanent DB, no 30-day expiry).
2. **Render** free web service (no credit card).
3. Accept **30–60 second cold starts** after 15 minutes idle.
4. **Never** use Render's free Postgres — it expires after 30 days.

See Northflank's own [FastAPI + Postgres guide](https://northflank.com/guides/deploy-fastapi-postgres-cloud-docker) for additional platform-specific details.

---

## Quick reference: local vs beta production

| | Local dev | Beta (Northflank Sandbox) |
|--|-----------|----------------------------|
| Database | SQLite (`dev.db`) | Northflank Postgres addon |
| `ENV` | `development` | `production` |
| HTTPS | No | Yes (automatic) |
| Password reset | Logged to console | Email (when implemented) |
| Cold starts | No | **No** (Sandbox always-on) |
| Start command | `uvicorn app.main:app --reload` | `scripts/start.sh` (migrations + uvicorn) |
| Credit card | No | Yes (verification only) |

---

## Related docs

- [BETA_DEPLOY.md](./BETA_DEPLOY.md) — private beta quick start
- [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) — MVP feature phases (all complete)
- [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) — architecture, schema, routes
- [DECISION_LOG.md](./DECISION_LOG.md) — design decisions (auth, audit, rate limits, email deferral)
