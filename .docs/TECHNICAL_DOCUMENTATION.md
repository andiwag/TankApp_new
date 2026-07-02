# Tankly – Full Technical Documentation

## Documentation index

| Document | Purpose |
|----------|---------|
| **This file** | Product spec, architecture, models, routes |
| [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) | Phased build plan (Phases 0–23) |
| [DECISION_LOG.md](./DECISION_LOG.md) | Architectural decisions |
| [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md) | Planned operator dashboard |
| [STRIPE_BILLING.md](./STRIPE_BILLING.md) | Planned billing integration |
| [BETA_DEPLOY.md](./BETA_DEPLOY.md) / [PRODUCTION.md](./PRODUCTION.md) | Deployment |

---

## 1. Product Overview

**Tankly** (`app/branding.py`: `PRODUCT_NAME`, domain `tankly.at`) is a SaaS web application for **farmers** to collaboratively track:

* fuel usage and consumption
* vehicles and machinery
* operating hours (tractors & machinery) and mileage (cars & motorcycles)
* maintenance logs and service reminders
* fuel costs and CSV export
* group analytics

The system allows **multiple users** in a **shared group** (farm/business) with role-based access.

**Implemented (Phases 0–21):** auth, groups, vehicles, fuel entries, summary, dashboard, profile, group settings, audit log UI, maintenance, analytics, export, cost tracking, marketing/landing, private-beta registration gate, PWA, production hardening, German UI across authenticated app.

**Planned:** platform operator dashboard ([PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md)), Stripe billing ([STRIPE_BILLING.md](./STRIPE_BILLING.md)).

**Future expansion paths:**

* OCR entry from receipts
* richer offline entry workflows
* deeper fleet analytics
* customer-initiated temporary support access (GDPR-friendly)

---

# 2. Core Concepts

### Groups (multi-user environments)

A **group** represents an organization (e.g. a farm).

Users inside a group can:

* create vehicles
* log fuel entries
* view statistics
* collaborate on shared data

Users can belong to multiple groups, but typically will only use one.

---

### Vehicles

Vehicles are tracked either by:

| vehicle type | usage unit |
| ------------ | ---------- |
| car          | km         |
| motorcycle   | km         |
| tractor      | hours      |
| machine      | hours      |

The `usage_unit` is **automatically derived** from the vehicle type during creation and is not user-editable (see DECISION_LOG.md D-002).

---

### Fuel Entries

Fuel entries represent a fueling event.

Each entry records:

* fuel amount (liters)
* usage reading at time of fueling (km or hours)
* full/partial tank flag
* optional total cost in EUR
* vehicle
* user
* date
* notes (optional, max 500 chars)

This enables consumption analytics (see Section 14 for calculation logic).

---

### Roles

| role        | permissions                               |
| ----------- | ----------------------------------------- |
| admin       | full access, manage members, delete group |
| contributor | create & edit entries and vehicles         |
| reader      | view only                                 |

---

# 3. Tech Stack

## Backend

* FastAPI
* SQLAlchemy ORM
* Alembic migrations
* Pydantic validation
* bcrypt password hashing
* session-based authentication (signed cookies via itsdangerous + DB-backed session records)

## Database

* SQLite (development)
* PostgreSQL (production ready)

## Frontend

* Jinja2 templates
* Tailwind CSS + Alpine.js — **self-hosted** under `app/static/vendor/` (no CDN in production CSP)

## PWA

* manifest.json
* service worker
* installable mobile experience

## Supporting libraries

* fastapi-mail (password reset and service reminder emails when `MAIL_*` configured)
* fastapi-csrf-protect (CSRF protection)
* itsdangerous (signed session cookies, password reset tokens)
* pydantic-settings (environment configuration)
* redis (optional — shared rate limits in production)
* sentry-sdk (optional error tracking)
* python-dotenv
* python-multipart (form handling)
* aiofiles (static file serving)
* uvicorn

## Testing

* pytest
* pytest-asyncio
* httpx (async test client)

---

# 4. System Architecture

### High-level architecture

Client (browser)
↓
FastAPI server
↓
SQLAlchemy ORM
↓
Database (SQLite/Postgres)

Server-side rendering is used instead of SPA architecture.

Benefits:

* simpler codebase
* faster development
* SEO friendly
* no frontend build pipeline
* fewer dependencies

### Authentication architecture

Session identity is stored in **signed cookies** using `itsdangerous`. The cookie contains minimal claims (`user_id`, `active_group_id`, `session_id`), while `UserSession` rows provide expiry and revocation. This keeps SSR form auth simple while allowing logout/password-change flows to invalidate sessions. See DECISION_LOG.md D-001 and D-046.

**Redis** (`REDIS_URL`) is optional in development; **required in multi-worker production** unless `SINGLE_WORKER_MODE=true` (beta only) for shared rate limits.

### Application layering

Routes own HTTP concerns: dependencies, form parsing, redirects, flash messages, template selection, and response status mapping.

Services own domain concerns: scoped queries, mutations, aggregate context builders, membership checks, invite-code generation, exports, reminders, and analytics calculations.

Templates own presentation only. Shared Jinja setup lives in `app/templating.py`, shared response helpers in `app/responses.py`, and shared membership/query helpers in `app/services/`.

---

# 5. Project Structure

```
Tankly/   (repo folder may be TankApp_new)

app/
    main.py              # FastAPI app, middleware, routers
    config.py            # Settings (see .env.example)
    database.py
    models.py
    schemas.py
    auth.py              # Password hashing, session cookie encode/decode
    audit.py
    dependencies.py      # Auth, active group, require_role
    branding.py          # PRODUCT_NAME, cookie defaults
    csrf.py
    rate_limit.py        # In-memory or Redis limiters
    services/            # Business logic (groups, vehicles, fuel, …)
    routes/
        auth.py
        marketing.py     # Landing, legal pages, robots.txt
        groups.py
        group_settings.py
        dashboard.py
        summary.py
        analytics.py
        vehicles.py
        fuel_entries.py
        maintenance.py
        export.py
        profile.py
        audit_log.py
        cron.py          # Bearer CRON_SECRET
    templates/
    static/              # PWA, vendor JS/CSS, icons

tests/                   # ~371 tests — see DEVELOPMENT_PLAN.md
.docs/                   # All project documentation
```

---

# 6. Database Design

## Entity Relationship Overview

User
↓ many-to-many (via UserGroup)
Group
↓ one-to-many
Vehicle
↓ one-to-many
FuelEntry
MaintenanceLog

UserSession → User (server-side auth sessions)
AuditLog → User, Group (nullable group_id)

`group_id` on FuelEntry is an **intentional denormalization** for query performance — see DECISION_LOG.md D-003.

---

# 7. Database Schema

## User

Represents an account.

```
User

id              int PK
email           string unique
name            string
password_hash   string

created_at      datetime
deleted_at      datetime nullable
```

Supports soft delete to preserve referential integrity with FuelEntries (see DECISION_LOG.md D-005).

---

## Group

Represents a shared environment.

```
Group

id                  int PK

name                string

invite_code         string unique

subscription_tier   string nullable

created_by          FK -> User.id

created_at          datetime
deleted_at          datetime nullable
```

---

## UserGroup

Associates users with groups.

```
UserGroup

user_id     FK -> User.id
group_id    FK -> Group.id

role        enum(admin, contributor, reader)

joined_at   datetime
```

Composite PK:
(user_id, group_id)

---

## Vehicle

Represents trackable equipment.

```
Vehicle

id              int PK

group_id        FK -> Group.id

name            string

vtype           enum
                car
                tractor
                motorcycle
                machine

usage_unit      enum
                km
                hours
                (auto-derived from vtype, not user-editable)

fuel_type       enum
                diesel
                petrol

created_at      datetime
updated_at      datetime
deleted_at      datetime nullable
```

`usage_unit` mapping: car/motorcycle → km, tractor/machine → hours (see DECISION_LOG.md D-002).

---

## FuelEntry

Represents a fueling event.

```
FuelEntry

id              int PK

vehicle_id      FK -> Vehicle.id
group_id        FK -> Group.id (denormalized, must match vehicle.group_id)
user_id         FK -> User.id

fuel_amount_l   float

usage_reading   float
                km or hours reading at fueling time

full_tank       bool (default true — partial fills excluded from consumption)
total_cost_eur  float nullable

notes           string nullable (max 500 chars)

entry_date      date

created_at      datetime
updated_at      datetime

deleted_at      datetime nullable
```

---

## MaintenanceLog

Service/maintenance records per vehicle (Phase 17).

```
MaintenanceLog

id                  int PK
vehicle_id          FK -> Vehicle.id
group_id            FK -> Group.id
user_id             FK -> User.id
service_date        date
usage_reading       float nullable
description         string (max 500)
cost_eur            float nullable
next_service_date   date nullable
next_service_usage  float nullable
reminder_sent_at    datetime nullable
created_at / updated_at / deleted_at
```

---

## UserSession

Server-side session for revocation (D-046).

```
UserSession

id          string PK (UUID)
user_id     FK -> User.id
created_at  datetime
expires_at  datetime
revoked_at  datetime nullable
```

---

## AuditLog

Tracks important structural events. Does **not** log routine data entry operations.

```
AuditLog

id          int PK

group_id    FK -> Group.id nullable
user_id     FK -> User.id

action      string
entity_type string
entity_id   int

created_at  datetime
```

Logged events: `user.register`, `group.create`, `group.delete`, `group.join`, `group.leave`, `member.role_change`, `member.remove`, `vehicle.create`, `vehicle.delete`, `maintenance.create`, `maintenance.update`, `maintenance.delete`

Not logged: `fuel_entry.*`, `vehicle.edit`, `user.login`, `user.logout`

Farm admins view history at `GET /settings/audit`. Planned: `platform.*` events for operator access (Phase 22).

---

# 8. Pydantic Schemas

## User

```
UserCreate

email
name
password
password_confirm
```

```
UserLogin

email
password
```

```
UserUpdate

name optional
email optional
```

```
PasswordChange

current_password
new_password
new_password_confirm
```

```
PasswordResetRequest

email
```

```
PasswordResetConfirm

token
new_password
new_password_confirm
```

---

## Vehicle

```
VehicleCreate

name
vtype
fuel_type
```

`usage_unit` is not in the schema — it is auto-derived from `vtype`.

```
VehicleUpdate

name optional
fuel_type optional
```

`vtype` is not editable after creation (changing type would invalidate existing usage readings).

---

## FuelEntry

```
FuelEntryCreate

vehicle_id
fuel_amount_l
usage_reading
entry_date
notes optional
```

```
FuelEntryUpdate

fuel_amount_l optional
usage_reading optional
entry_date optional
notes optional
```

---

## Group

```
GroupCreate

name
```

```
JoinGroup

invite_code
```

---

# 9. Authentication

Session-based authentication uses **signed cookies** (via `itsdangerous`) plus DB-backed `UserSession` records.

### Flow

Register:

POST /register

validate input (email, name, password, password_confirm)

hash password using bcrypt

store user

create `UserSession`

create signed session cookie containing `session_id`

redirect to group selection

---

Login:

POST /login

verify password

create `UserSession`

create signed session cookie containing `session_id`

redirect to dashboard (or group selection if no groups)

---

Session structure (signed cookie payload):

```
session_id          UUID → user_sessions.id
user_id
active_group_id     nullable
platform_view       optional (Phase 22 — planned)
platform_view_group_id  optional (Phase 22 — planned)
```

---

Logout:

POST /logout

revoke the current `UserSession`, clear session cookie, redirect to login

---

Password Reset:

POST /forgot-password → generate reset token, send email (or log in dev mode)

GET /reset-password/{token} → render reset form

POST /reset-password/{token} → validate token, update password

Tokens expire after 1 hour. Non-existent emails return success silently (prevent email enumeration).

When `settings.mail_configured`, reset links are sent via SMTP (`app/mail.py`). Otherwise development may log the link; production should configure Brevo — see [BETA_DEPLOY.md](./BETA_DEPLOY.md).

---

# 10. Authorization

Role-based access control.

Dependency example:

```
require_role("admin")
```

Permission matrix:

| action              | admin | contributor | reader |
| ------------------- | ----- | ----------- | ------ |
| view data           | yes   | yes         | yes    |
| create vehicle      | yes   | yes         | no     |
| edit vehicle        | yes   | yes         | no     |
| delete vehicle      | yes   | no          | no     |
| add fuel entry      | yes   | yes         | no     |
| edit fuel entry     | yes   | yes         | no     |
| delete fuel entry   | yes   | no          | no     |
| manage members      | yes   | no          | no     |
| change member roles | yes   | no          | no     |
| regenerate invite   | yes   | no          | no     |
| delete group        | yes   | no          | no     |

---

# 11. Group System

Users can:

* create group (becomes admin)
* join group via invite code (becomes contributor)
* switch active group
* leave group (sole admin cannot leave)

Admins can:

* soft-delete group
* regenerate invite code
* change member roles
* remove members

---

Invite code format example:

FARM-82KD9

Codes are:

* unique
* reusable
* regeneratable (old code stops working when regenerated)

---

# 12. Application Flow

```
Landing / Login / Register
        ↓
Select or Create Group (if no groups)
        ↓
Dashboard
    ↓      ↓        ↓         ↓          ↓         ↓
Vehicles  Fuel  Maintenance  Summary  Analytics  Settings  Profile
                                              ↓
                                         Export CSV
```

Operators (planned): `/platform/farms` → optional “view farm” → same app UI read-only.

---

# 13. Routes Overview

## Auth

GET /login

POST /login

GET /register

POST /register

POST /logout

GET /forgot-password

POST /forgot-password

GET /reset-password/{token}

POST /reset-password/{token}

---

## Groups

GET /groups

POST /groups/create

POST /groups/join

POST /groups/switch/{id}

POST /groups/leave/{id}

POST /groups/delete/{id}

---

## Dashboard

GET /dashboard

Displays:

* total vehicles
* total fuel entries
* total fuel liters
* recent fuel entries

---

## Vehicles

GET /vehicles

GET /vehicles/new

POST /vehicles/new

GET /vehicles/{id}/edit

POST /vehicles/{id}/edit

POST /vehicles/{id}/delete

---

## Fuel Entries

GET /fuel

GET /fuel/new

POST /fuel/new

GET /fuel/{id}/edit

POST /fuel/{id}/edit

POST /fuel/{id}/delete

---

## Summary

GET /summary

Displays:

* fuel per vehicle (total liters, entry count)
* total fuel per month (last 12 months)
* consumption averages per vehicle

---

## Group Settings

GET /settings/group

POST /settings/group/regenerate-code

POST /settings/group/members/{user_id}/role

POST /settings/group/members/{user_id}/remove

Displays:

* invite code (with copy button)
* member list with roles
* role change controls (admin only)
* remove member controls (admin only)
* link to audit log (`/settings/audit`, admin only)
* danger zone (delete group)

---

## Profile

GET /profile

POST /profile

POST /profile/change-password

POST /profile/sessions/{id}/revoke

---

## Maintenance

GET /maintenance — list

GET/POST /maintenance/new, edit, delete — contributor+ / admin delete

---

## Analytics

GET /analytics — group charts and context

---

## Export

GET /export/fuel-entries.csv

GET /export/vehicles.csv

---

## Audit log

GET /settings/audit — farm admin only

---

## Marketing & legal

GET / — landing (redirect if logged in)

GET /impressum, /datenschutz, /agb

GET /robots.txt

---

## Health & cron

GET /health — liveness

GET /health/ready — DB readiness

POST /cron/service-reminders — `Authorization: Bearer <CRON_SECRET>`

---

## Platform admin (planned)

GET /platform/farms, /platform/users, … — see [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md)

---

# 14. Statistics & Consumption Calculation

## Dashboard metrics (MVP)

* vehicles count
* entries count
* total liters
* recent entries (last 5–10)

## Summary page metrics

* fuel per vehicle (total liters, entry count)
* total fuel per month (last 12 months)
* consumption averages per vehicle

## Consumption calculation logic

Formula:
* **km-based vehicles (car, motorcycle):** `fuel_amount_l / (current_reading - previous_reading) * 100` → **L/100km**
* **hours-based vehicles (tractor, machine):** `fuel_amount_l / (current_reading - previous_reading)` → **L/h**

Rules:
1. "Previous reading" = the most recent fuel entry for the same vehicle with a **lower** `usage_reading`, sorted by `usage_reading` (not by `entry_date`).
2. **First entry** for a vehicle: no consumption value (needs at least 2 data points).
3. **Out-of-order entries:** Sorting by `usage_reading` handles this correctly.
4. Only entries marked as full-tank fills participate in consumption segments. Partial fills (`full_tank=false`) are stored for volume and cost history but excluded from average consumption calculations.

Partial fills remain useful for total liters, costs, exports, and auditability even when they do not produce reliable consumption segments.

See DECISION_LOG.md D-004 and D-048.

---

# 15. Security

Password hashing:
bcrypt

Session cookies:
* httpOnly
* secure (production)
* sameSite

CSRF protection:
fastapi-csrf-protect (all unsafe requests require a valid signed-cookie + form-field CSRF token)

Soft deletes:
`deleted_at` fields on User, Group, Vehicle, FuelEntry, and MaintenanceLog

Session revocation:
`UserSession` rows support revoking individual sessions and invalidating sessions after security-sensitive actions.

Group filtering:
all queries scoped to `active_group_id`

Rate limiting:
login, register, and password reset routes are rate-limited

Email enumeration prevention:
password reset always returns success regardless of email existence

---

# 16. PWA Configuration

manifest.json

```
name
short_name

display standalone

icons 192 and 512
```

Service worker caches:

* manifest
* icons
* static assets under `/static/`

Goal:

installable mobile web app

---

# 17. Environment Variables

.env example:

```
DATABASE_URL=sqlite:///./dev.db

SECRET_KEY=supersecretkey

SESSION_COOKIE_NAME=tankly_session

ENV=development

BASE_URL=

REDIS_URL=
SINGLE_WORKER_MODE=false

CRON_SECRET=

REGISTRATION_INVITE_CODE=

ALLOWED_HOSTS=*

SENTRY_DSN=

RUN_MIGRATIONS_ON_START=true

MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=noreply@tankly.at
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_STARTTLS=true

# Planned (Phase 22) — see PLATFORM_ADMIN.md
# PLATFORM_ADMIN_EMAILS=
```

See `.env.example` and `.env.beta.example` for the canonical list. Production requires unique `SECRET_KEY`, `CRON_SECRET`, and Redis or `SINGLE_WORKER_MODE=true`.

---

# 18. Scalability Considerations

PostgreSQL compatibility

soft deletes preserve analytics

group-based architecture supports SaaS growth

schema supports:

* multiple farms
* multiple employees
* large datasets

Denormalized `group_id` on FuelEntry optimizes the most common query pattern.

---

# 19. Future Features

* OCR fuel receipt scanning
* Platform operator dashboard (Phase 22 — [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md))
* Stripe subscription billing (Phase 23 — [STRIPE_BILLING.md](./STRIPE_BILLING.md))
* richer offline entry workflows
* deeper fleet analytics
* customer-initiated temporary support access (GDPR-friendly)

---

# 20. Implementation Order

**Completed:** Phases 0–21 (see [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md))

1. project setup & test infrastructure
2. database, models, schemas, migrations
3. authentication & password reset
4. groups & roles
5. base template & layout
6. dashboard, vehicles, fuel entries
7. profile, summary, group settings
8. audit logging (+ admin UI in Phase 19)
9. CSRF, PWA, validation polish
10. maintenance, analytics, export, cost/partial fill
11. session revocation, production hardening, marketing/beta gate

**Planned next:**

12. platform admin (Phase 22)
13. Stripe billing (Phase 23)

Development follows a strict **test-driven** approach (Red → Green → Refactor).
See `DEVELOPMENT_PLAN.md` for detailed phase breakdowns, test lists, and acceptance criteria.
