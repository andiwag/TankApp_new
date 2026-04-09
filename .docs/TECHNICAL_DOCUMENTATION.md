# TankApp SaaS – Full Technical Documentation

## 1. Product Overview

**TankApp** is a SaaS web application designed primarily for **farmers** to collaboratively track:

* fuel usage
* vehicles
* operating hours (tractors & machinery)
* mileage (cars & motorcycles)

The system allows **multiple users** to work within a **shared group environment** (e.g. a farm business), ensuring accurate and consistent fuel tracking.

Future expansion paths include:

* OCR entry from receipts
* cost tracking
* maintenance tracking
* reporting & export
* mobile offline functionality

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
* session-based authentication (signed cookies via itsdangerous)

## Database

* SQLite (development)
* PostgreSQL (production ready)

## Frontend

* Jinja2 templates
* Tailwind CSS (CDN)
* Alpine.js (light interactivity)

## PWA

* manifest.json
* service worker
* installable mobile experience

## Supporting libraries

* fastapi-mail (password reset emails)
* fastapi-csrf-protect (CSRF protection)
* itsdangerous (signed session cookies, password reset tokens)
* pydantic-settings (environment configuration)
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

Session data (`user_id`, `active_group_id`) is stored in **signed cookies** using `itsdangerous`. This keeps the server stateless — no session table, no Redis. See DECISION_LOG.md D-001.

---

# 5. Project Structure

```
TankApp/

app/

    __init__.py

    main.py
        FastAPI app initialization
        middleware
        router registration

    config.py
        environment settings
        database URL
        secret keys

    database.py
        SQLAlchemy engine
        session factory

    models.py
        SQLAlchemy ORM models

    schemas.py
        Pydantic schemas

    auth.py
        password hashing
        session cookie creation/decoding

    audit.py
        audit log helper function

    dependencies.py
        auth dependencies
        role guards

    routes/

        auth.py
            login
            register
            logout
            password reset

        dashboard.py
            main dashboard
            statistics overview

        vehicles.py
            CRUD operations

        fuel_entries.py
            CRUD operations

        groups.py
            group management

        group_settings.py
            invite code management
            member management
            role changes

        summary.py
            fuel per vehicle
            monthly totals
            consumption averages

        profile.py
            view/edit profile
            change password

    templates/

        base.html
        login.html
        register.html
        forgot_password.html
        reset_password.html
        groups.html
        dashboard.html

        vehicles.html
        vehicle_form.html

        fuel_entries.html
        fuel_entry_form.html

        summary.html

        group_settings.html

        profile.html

    static/

        manifest.json
        sw.js

        icon-192.png
        icon-512.png

tests/

    __init__.py
    conftest.py
    test_config.py
    test_models.py
    test_schemas.py
    test_auth.py
    test_groups.py
    test_vehicles.py
    test_fuel_entries.py
    test_dashboard.py
    test_summary.py
    test_profile.py
    test_group_settings.py
    test_audit_log.py

requirements.txt
.env.example

.docs/
    TECHNICAL_DOCUMENTATION.md
    DEVELOPMENT_PLAN.md
    DECISION_LOG.md

.prompts/
    AGENT_PROMPT.md
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

AuditLog references User and Group.

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

notes           string nullable (max 500 chars)

entry_date      date

created_at      datetime
updated_at      datetime

deleted_at      datetime nullable
```

---

## AuditLog

Tracks important structural events. Does **not** log routine data entry operations.

```
AuditLog

id          int PK

group_id    FK -> Group.id
user_id     FK -> User.id

action      string
entity_type string
entity_id   int

created_at  datetime
```

Logged events: `user.register`, `group.create`, `group.delete`, `group.join`, `group.leave`, `member.role_change`, `member.remove`, `vehicle.create`, `vehicle.delete`

Not logged: `fuel_entry.*`, `vehicle.edit`, `user.login`, `user.logout`

See DECISION_LOG.md D-006 for rationale.

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

Session-based authentication using **signed cookies** (via `itsdangerous`).

### Flow

Register:

POST /register

validate input (email, name, password, password_confirm)

hash password using bcrypt

store user

create signed session cookie

redirect to group selection

---

Login:

POST /login

verify password

create signed session cookie

redirect to dashboard (or group selection if no groups)

---

Session structure (stored in signed cookie):

```
session

user_id
active_group_id
```

---

Logout:

POST /logout

clear session cookie

redirect to login

---

Password Reset:

POST /forgot-password → generate reset token, send email (or log in dev mode)

GET /reset-password/{token} → render reset form

POST /reset-password/{token} → validate token, update password

Tokens expire after 1 hour. Non-existent emails return success silently (prevent email enumeration).

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
Login / Register
        ↓
Select or Create Group (if no groups)
        ↓
Dashboard
    ↓      ↓       ↓       ↓       ↓
Vehicles  Entries  Stats  Settings  Profile
```

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
* danger zone (delete group)

---

## Profile

GET /profile

POST /profile

POST /profile/change-password

Displays:

* name and email (editable)
* password change form

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
4. **Assumption:** All fills are **full tank fills**. Partial fills are not tracked in MVP.

Limitation: Partial fills will produce inaccurate consumption numbers. A `full_tank` boolean field could be added later.

See DECISION_LOG.md D-004 for full rationale.

---

# 15. Security

Password hashing:
bcrypt

Session cookies:
* httpOnly
* secure (production)
* sameSite

CSRF protection:
fastapi-csrf-protect (required — all POST forms include CSRF token)

Soft deletes:
`deleted_at` fields on User, Group, Vehicle, FuelEntry

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

* CSS
* JS
* templates
* icons

Goal:

installable mobile web app

---

# 17. Environment Variables

.env example:

```
DATABASE_URL=sqlite:///./dev.db

SECRET_KEY=supersecretkey

SESSION_COOKIE_NAME=tankapp_session

ENV=development

MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=noreply@tankapp.example.com
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_STARTTLS=true
```

In development mode, password reset emails are logged to console instead of sent.

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
* cost tracking
* maintenance logs
* service reminders
* data export
* offline support
* analytics dashboard
* mobile optimization
* subscription billing
* partial fill tracking (`full_tank` boolean)

---

# 20. Implementation Order

1. project setup & test infrastructure
2. database setup
3. models
4. pydantic schemas
5. migrations
6. authentication (register, login, logout)
7. password reset
8. groups
9. base template & layout
10. dashboard
11. vehicles CRUD
12. fuel entries CRUD
13. user profile management
14. summary & statistics
15. group settings
16. audit logging
17. CSRF protection
18. PWA support
19. validation & polish

Development follows a strict **test-driven** approach (Red → Green → Refactor).
See `DEVELOPMENT_PLAN.md` for detailed phase breakdowns, test lists, and acceptance criteria.
