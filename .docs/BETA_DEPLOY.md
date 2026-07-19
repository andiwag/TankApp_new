# Tankly – Private Beta Deployment

Step-by-step guide to deploy Tankly for a **private beta** with 1–2 invited farms. For full production (billing, legal, paid hosting), see [PRODUCTION.md](./PRODUCTION.md) and [STRIPE_BILLING.md](./STRIPE_BILLING.md).

**Related:** [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) (Phases 0–21 complete), [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md) (Phase 1 operator dashboard implemented; Phase 2 support view planned).

---

## What you need

| Item | Notes |
|------|--------|
| GitHub repo pushed | CI must be green on `main` |
| Northflank account | Sandbox tier ($0) — [northflank.com](https://northflank.com) |
| Brevo account (optional) | Free SMTP for password reset + service reminders |
| Invite code | Share with beta farms only |

---

## 1. Generate secrets

```powershell
.\scripts\generate-beta-secrets.ps1
```

Copy the three lines into a password manager. You will paste them into Northflank in step 4.

Set `REGISTRATION_INVITE_CODE` to gate registration — only people with the code can create accounts. This also enables `noindex` and `robots.txt` blocking so the beta stays off search engines.

---

## 2. Push code

Ensure these files are on `main`:

- `Dockerfile` (installs `requirements-prod.txt`)
- `scripts/start.sh`, `scripts/migrate.sh`
- `requirements-prod.txt`, `requirements-dev.txt`
- Self-hosted frontend assets in `app/static/vendor/`

**Local dev:** Python **3.12** required. Install deps with `pip install -r requirements-dev.txt`.

CI runs lint, full pytest on Postgres (with coverage), and a Docker build on every push.

---

## 3. Create Northflank resources

### Postgres addon

1. **Create new → Addon → PostgreSQL** — name `Tankly-db`
2. Keep networking **internal**
3. Optional: enable backup schedule

### Secret group (recommended)

1. **Create new → Secret group**
2. Link `Tankly-db` addon
3. Map `POSTGRES_URI` → alias **`DATABASE_URL`**

### Web service

1. **Create new → Service → Combined service** — name `Tankly-web`
2. Repository: `TankApp_new` (or your fork), branch `main`
3. Build: **Dockerfile** at repo root
4. Public HTTP enabled → note your `https://….code.run` URL
5. Health check: **`/health/ready`** (readiness)
6. Link secret group from above

---

## 4. Environment variables

Set on the `Tankly-web` service (see `.env.beta.example`):

| Variable | Value |
|----------|--------|
| `SECRET_KEY` | From generate script |
| `CRON_SECRET` | From generate script |
| `REGISTRATION_INVITE_CODE` | From generate script — share with beta farms |
| `PLATFORM_ADMIN_EMAILS` | Your operator email(s) — enables `/platform` dashboard |
| `ENV` | `production` |
| `SINGLE_WORKER_MODE` | `true` |
| `BASE_URL` | `https://your-app.code.run` |
| `ALLOWED_HOSTS` | `your-app.code.run` |
| `DATABASE_URL` | From secret group (if not linked automatically) |

**Email (recommended):**

```
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_STARTTLS=true
MAIL_USERNAME=<brevo login>
MAIL_PASSWORD=<brevo smtp key>
MAIL_FROM=noreply@yourdomain.com
```

---

## 5. Service reminder cron (optional)

1. **Create new → Cron Job** (or use external scheduler)
2. Schedule: daily, e.g. `0 7 * * *`
3. Request:
   ```
   POST https://your-app.code.run/cron/service-reminders
   Authorization: Bearer <CRON_SECRET>
   ```

Requires mail env vars and `BASE_URL`.

---

## 6. Post-deploy verification

Run on the live URL:

- [ ] `GET /health` → `{"status":"ok"}`
- [ ] `GET /health/ready` → `{"status":"ready"}`
- [ ] `GET /` → landing page loads
- [ ] `GET /robots.txt` → `Disallow: /` (when invite code is set)
- [ ] Register **without** invite code → blocked
- [ ] Register **with** invite code → success → create group
- [ ] Add vehicle + fuel entry → dashboard updates
- [ ] Forgot password (if mail configured)
- [ ] Profile → download personal data (JSON)
- [ ] Second browser: join group via invite code

---

## 7. Onboard beta farms

1. Send them the app URL and **registration invite code** (not the group invite code — that's created after they register).
2. Farm admin registers → creates a group → shares `FARM-XXXXX` with workers.
3. Workers join with group invite code; assign **contributor** or **reader** roles.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| App won't start | Check logs — usually missing `SECRET_KEY`, `CRON_SECRET`, or `DATABASE_URL` |
| `ValidationError` on boot | Set `SINGLE_WORKER_MODE=true` or add `REDIS_URL` |
| CSRF errors | Ensure `ENV=production` and you're on HTTPS |
| 502 bad gateway | App must listen on `$PORT` (handled by `scripts/start.sh`) |
| Password reset silent | Set all `MAIL_*` vars and `BASE_URL` |

---

## Related docs

- [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) — phase status (0–23 complete)
- [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) — architecture reference
- [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md) — operator dashboard (Phase 22)
- [PRODUCTION.md](./PRODUCTION.md) — full deployment reference
- [STRIPE_BILLING.md](./STRIPE_BILLING.md) — billing (Phase 23)
- [STRIPE_GO_LIVE.md](./STRIPE_GO_LIVE.md) — when you're ready to charge in production
