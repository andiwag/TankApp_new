# Tankly – Platform Admin & Operator Dashboard

Implementation guide for **internal operator tooling** — the layer that lets you (as product owner / support) see all deployed farms, inspect users, and troubleshoot customer issues. This is separate from **farm admin**, which customers use to manage their own group.

**Status:** Phase 1–2 implemented — **Development Plan Phase 22 complete**. Phase 3 hardening optional.

**Prerequisites:** Phases 0–21 complete in the app. Billing fields in operator UI depend on Phase 23 — see [STRIPE_BILLING.md](./STRIPE_BILLING.md).

**Related docs:** [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) (Phase 22) · [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) · [BETA_DEPLOY.md](./BETA_DEPLOY.md) · [PRODUCTION.md](./PRODUCTION.md)

---

## Table of contents

1. [Why this exists](#1-why-this-exists)
2. [Current state vs target state](#2-current-state-vs-target-state)
3. [Permission model (two layers)](#3-permission-model-two-layers)
4. [Implementation phases](#4-implementation-phases)
5. [Environment variables](#5-environment-variables)
6. [Architecture & new files](#6-architecture--new-files)
7. [Phase 1 – Read-only operator dashboard](#7-phase-1--read-only-operator-dashboard)
8. [Phase 2 – View farm (support access)](#8-phase-2--view-farm-support-access)
9. [Phase 3 – Production hardening](#9-phase-3--production-hardening)
10. [Audit logging for platform actions](#10-audit-logging-for-platform-actions)
11. [UI & templates](#11-ui--templates)
12. [Security rules](#12-security-rules)
13. [Testing](#13-testing)
14. [Production checklist](#14-production-checklist)
15. [Alternatives & when to use them](#15-alternatives--when-to-use-them)
16. [Open decisions (for DECISION_LOG)](#16-open-decisions-for-decision_log)
17. [Implementation pitfalls (review checklist)](#17-implementation-pitfalls-review-checklist)

---

## 1. Why this exists

Tankly is **multi-tenant**: each farm is a `Group` in the database. Customers get **farm-level** roles (`admin`, `contributor`, `reader`) via the `UserGroup` join table. That model is correct for customers but **does not give you cross-farm visibility**.

Without a platform admin layer you cannot reliably:

- See which farms are deployed and active
- Look up a user by email and see which farms they belong to
- Answer support questions (“Is their farm set up? How many vehicles?”)
- Verify subscription tier / billing status across farms (once Stripe is live)
- Debug “what does the customer see?” without joining every farm manually

**Industry norm:** B2B SaaS products ship an internal **operator dashboard** (`/platform`, `/admin`, or a separate subdomain). Raw database access is break-glass only, not daily workflow.

---

## 2. Current state vs target state

### Current state (as of this doc)

| Area | Status |
|------|--------|
| Farm = `Group` model | ✅ Implemented |
| Farm roles (`admin` / `contributor` / `reader`) | ✅ Per-group via `UserGroup` |
| `require_role("admin")` | ✅ Checks role in **active group only** |
| `/groups` | ✅ Lists **only farms the user belongs to** |
| `/settings/group` | ✅ Farm admin: members, invite code, roles |
| Platform admin flag on `User` | ❌ Not implemented |
| `/platform/*` routes | ❌ Not implemented |
| Cross-farm queries | ❌ Not implemented |
| Support “view as farm” | ❌ Not implemented (Phase 22 — see [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md)) |

Relevant existing code:

- `app/models.py` — `User`, `Group`, `UserGroup` (no platform flag)
- `app/dependencies.py` — `require_role()`, membership checks on active group
- `app/services/groups.py` — `user_groups_context()` filters by `UserGroup.user_id`
- `app/audit.py` — `log_event()` for farm-scoped audit entries

### Target state

| Phase | Capability |
|-------|------------|
| **1** | Read-only `/platform` dashboard: all farms, farm detail, user search |
| **2** | “View farm” — enter a farm as platform support (read-only), with banner + audit |
| **3** | MFA, optional IP allowlist, billing columns, customer-initiated support grant (optional) |

---

## 3. Permission model (two layers)

Keep these **completely separate**. Do not overload farm `admin` to mean platform operator.

```
┌─────────────────────────────────────────────────────────────┐
│  Platform admin (you / your team)                           │
│  Scope: ALL farms, ALL users (operator routes only)         │
│  Grant: PLATFORM_ADMIN_EMAILS env allowlist (Phase 1)       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │  does NOT inherit
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Farm admin (customer)                                      │
│  Scope: ONE active group                                    │
│  Grant: UserGroup.role == "admin"                           │
└─────────────────────────────────────────────────────────────┘
```

### Farm admin (existing — do not change semantics)

- Managed in `/settings/group`
- Can change member roles, regenerate invite code, remove members
- `require_role(Role.admin.value)` in `app/dependencies.py`

### Platform admin (new)

- Access to `/platform/*` only when logged-in user’s email is in allowlist
- May **read** any group’s metadata without being a member (Phase 1)
- May **enter** a farm context for support viewing (Phase 2) — still not a farm `admin` unless explicitly designed otherwise
- All platform actions are **audit-logged** with a distinct action prefix (e.g. `platform.farm.detail`)

**Important:** Platform admin must **not** appear as a member on the customer’s group settings page unless you deliberately add a “support access” membership model (Phase 3 optional).

---

## 4. Implementation phases

### Overview

| Phase | Goal | Effort (estimate) | Ship when |
|-------|------|-------------------|-----------|
| **1** | Read-only ops dashboard | 1–2 days | Before selling / broad beta |
| **2** | View farm (support session) | 1 day | When first real support tickets appear |
| **3** | Hardening + billing in overview | Ongoing | Before paid launch at scale |

Phases are sequential. Phase 1 alone covers ~80% of early support needs.

---

## 5. Environment variables

Add to `app/config.py` and document in `.env.example` / [BETA_DEPLOY.md](./BETA_DEPLOY.md).

### Phase 1

```env
# Comma-separated list of operator emails (case-insensitive).
# Empty = no platform admin access (safe default).
PLATFORM_ADMIN_EMAILS=you@example.com,co-founder@example.com
```

**Parsing rules:**

- Split on `,`, strip whitespace, lower-case for comparison
- Compare against `user.email.lower()` at request time
- Empty string → feature disabled (no `/platform` access for anyone)

**Why env allowlist first (not a DB column):**

- Zero migration for solo/small team
- Easy to rotate (change env, redeploy)
- No risk of accidentally granting platform admin via farm settings UI
- Matches existing patterns (`REGISTRATION_INVITE_CODE`, `CRON_SECRET`)

**Later (optional):** `User.is_platform_admin` column if you need to grant/revoke without redeploying. Env allowlist can remain as override or bootstrap list.

### Phase 3 (optional)

```env
# Restrict /platform to these IPs (comma-separated). Empty = no IP filter.
PLATFORM_ADMIN_IP_ALLOWLIST=

# Require separate shared secret header for /platform (defence in depth).
# PLATFORM_ADMIN_HEADER_SECRET=
```

---

## 6. Architecture & new files

Follow existing conventions: thin routes, logic in services, Jinja templates.

### New modules

| File | Responsibility |
|------|----------------|
| `app/services/platform_admin.py` | Queries: list farms, farm detail, user search, stats aggregates |
| `app/routes/platform.py` | HTTP routes under `/platform` |
| `app/templates/platform_base.html` | Operator layout (distinct from customer nav) |
| `app/templates/platform_farms.html` | Farm list |
| `app/templates/platform_farm_detail.html` | Single farm: members, counts, links |
| `app/templates/platform_users.html` | User search results |
| `app/templates/platform_user_detail.html` | Single user + farm memberships |
| `tests/test_platform_admin.py` | Access control + query tests |

### Modified modules

| File | Change |
|------|--------|
| `app/config.py` | `PLATFORM_ADMIN_EMAILS` + helper `platform_admin_emails` property |
| `app/dependencies.py` | `require_platform_admin()` dependency |
| `app/main.py` | Register `platform_router`; optional `PlatformAdminException` handler → 403 |
| `app/auth.py` | Extend session cookie payload (Phase 2): `platform_view`, `platform_view_group_id` |
| `app/services/sessions.py` | Pass platform-view flags through `refresh_session_cookie` / `start_user_session` |
| `app/services/membership.py` | Optional: explicit `platform_view` handling in `group_page_capabilities()` |
| `app/middleware/session_cookie.py` | Must not clear `active_group_id` when `platform_view` is set (see §8.7) |
| `app/templates/base.html` | Phase 2: support banner when viewing farm as platform admin |

### Router registration

In `app/main.py`:

```python
from app.routes.platform import router as platform_router

app.include_router(platform_router)
```

Place **after** auth router so session middleware applies. Platform routes use the same CSRF protection as the rest of the app.

---

## 7. Phase 1 – Read-only operator dashboard

### 7.1 Config helper

```python
# app/config.py (sketch)

PLATFORM_ADMIN_EMAILS: str = ""

@property
def platform_admin_emails(self) -> frozenset[str]:
    if not self.PLATFORM_ADMIN_EMAILS.strip():
        return frozenset()
    return frozenset(
        e.strip().lower()
        for e in self.PLATFORM_ADMIN_EMAILS.split(",")
        if e.strip()
    )
```

### 7.2 Dependency

```python
# app/dependencies.py (sketch)

class PlatformAdminRequiredException(Exception):
    pass


def is_platform_admin(user: User) -> bool:
    from app.config import settings
    return user.email.lower() in settings.platform_admin_emails


def require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    if not is_platform_admin(user):
        raise PlatformAdminRequiredException()
    return user
```

Register handler in `main.py` → `forbidden_response()` (same as insufficient role).

**403 vs 404:** Return **403** for non-operators (consistent with `InsufficientRoleException`). Do not return 404 to “hide” the route — that adds complexity without real security. Keep error copy generic (“Forbidden”), not “Platform admin required”.

### 7.3 Routes (Phase 1)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/platform` | Redirect → `/platform/farms` |
| `GET` | `/platform/farms` | Paginated list of all groups |
| `GET` | `/platform/farms/{group_id}` | Farm detail: members, stats |
| `GET` | `/platform/users` | Search form (query param `q`) |
| `GET` | `/platform/users/{user_id}` | User detail + farm memberships |

All routes: `Depends(require_platform_admin)`.

**Not in Phase 1:** POST mutations (role changes, deletes, impersonation).

### 7.4 Service queries

Implement in `app/services/platform_admin.py`.

#### Farm list (`list_farms`)

Query `Group` with aggregates (use subqueries or `func.count` with `outerjoin`):

| Column | Source |
|--------|--------|
| ID | `Group.id` |
| Name | `Group.name` |
| Invite code | `Group.invite_code` (show masked in list: `FARM-•••••`, full on detail) |
| Created | `Group.created_at` |
| Status | `deleted_at IS NULL` → Active, else Deleted |
| Subscription tier | `Group.subscription_tier` (nullable → “free”) |
| Member count | `COUNT(UserGroup)` |
| Vehicle count | `COUNT(Vehicle)` where `deleted_at IS NULL` |
| Last activity | `MAX(FuelEntry.created_at)` or `MAX(AuditLog.created_at)` for group |

**Include soft-deleted farms** in a separate filter/tab (`?status=active|deleted|all`). Operators need to see deleted farms for support.

Default sort: `created_at DESC`.

**Pagination:** No list pagination exists elsewhere in the app today. For Phase 1 either (a) load all farms — fine while farm count is small (beta), or (b) add simple `page` / `per_page` (default 25) only on `/platform/farms`. Do not block Phase 1 on pagination if beta farm count is low.

**Search syntax:** Use case-insensitive match — PostgreSQL: `ilike()`; SQLite: `like()` with lowercased operands (app supports both via `DATABASE_URL`).

**Creator email:** `Group.created_by` is an FK to `User.id` but there is **no ORM relationship** on `Group` — join/query `User` explicitly in the service layer.

#### Farm detail (`farm_detail_context`)

For one `group_id`:

- Group metadata (creator user email via `created_by` → `User`)
- Members table: email, name, role, `joined_at`
- Counts: vehicles, fuel entries, maintenance logs (non-deleted)
- Recent audit log entries (last 20) — reuse query patterns from `app/services/audit_ui.py`
- Link: “View farm” (Phase 2 button, disabled or hidden until Phase 2)

#### User search (`search_users`)

- `GET /platform/users?q=email@example.com`
- Partial match on `User.email` and `User.name` (ILIKE)
- Exclude soft-deleted users by default (`deleted_at IS NULL`)
- Result: user id, email, name, created_at, list of farms + roles

#### User detail

- Profile fields (no password hash)
- All `UserGroup` rows with group name and role
- Active sessions count (optional, from `UserSession`)

### 7.5 N+1 prevention

Use `joinedload` / explicit joins for member lists. Platform pages are low-traffic but should still be efficient — one round-trip for farm list aggregates where possible.

### 7.6 Phase 1 checklist

- [ ] Add `PLATFORM_ADMIN_EMAILS` to config with tests for parsing
- [ ] Implement `is_platform_admin` / `require_platform_admin`
- [ ] Create `app/services/platform_admin.py` with list/detail/search
- [ ] Create routes + templates
- [ ] Register router in `main.py`
- [ ] Log `platform.farm.list` / `platform.farm.detail` / `platform.user.search` via audit (see §10)
- [ ] Write tests (see §13)
- [ ] Document env var in BETA_DEPLOY / `.env.example`
- [ ] Set your email in production Northflank secrets

---

## 8. Phase 2 – View farm (support access)

When a customer says “I don’t see X on the dashboard”, read-only metadata is not enough. Phase 2 lets you **open the farm** in the normal app UI without joining as a permanent member.

### 8.1 Session extension

Current session cookie payload (`app/auth.py`):

```python
{
    "session_id": "...",
    "user_id": 123,
    "active_group_id": 456,
}
```

Extend for platform viewing:

```python
{
    "session_id": "...",
    "user_id": 123,
    "active_group_id": 456,
    "platform_view": True,          # optional bool
    "platform_view_group_id": 456,  # redundant but useful for validation
}
```

**Rules:**

1. `platform_view` may only be set by `POST /platform/farms/{id}/enter` when `require_platform_admin` passes.
2. When `platform_view` is true, `_attach_user_to_request` in `dependencies.py` must set `active_group` **even if user is not in `UserGroup`** for that group.
3. Platform view is **read-only by default**: block all POST/PUT/DELETE on farm-scoped routes unless `platform_view` is false.

### 8.2 `require_role` must be platform-view aware

Membership bypass in `_attach_user_to_request` alone is **not enough**. Many routes also call `require_role(...)` which queries `UserGroup` and will **403** even on GET.

| Route pattern | Example | Works with membership bypass alone? |
|---------------|---------|-------------------------------------|
| `get_active_group` only | `/dashboard`, `/vehicles`, `/fuel`, `/summary`, `/analytics`, `/maintenance` | ✅ Yes |
| `require_role(contributor)` on GET | `/vehicles/new`, `/fuel/new`, edit forms | ❌ No — blocked on GET |
| `require_role(admin)` on GET | `/settings/audit` | ❌ No — blocked on GET |

**Required change:** Update `require_role()` (or add a shared helper) so when `session_data["platform_view"]` is true, the effective role is **`reader`** (not admin). That matches the “reader-level visibility” goal and blocks contributor/admin-only pages unless you deliberately elevate.

Pages a platform operator **can** browse in support view (after `require_role` fix):

- Dashboard, summary, analytics, vehicles list, fuel list, maintenance list, export CSV (see §8.3)

Pages still **blocked** (admin/contributor GET):

- `/settings/audit` (farm admin only — use `/platform/farms/{id}` audit excerpt instead)
- Create/edit forms (`/vehicles/new`, `/fuel/new`, …) — correct for read-only support

### 8.3 Read-only enforcement (mutations and exports)

Block **non-GET** requests when `platform_view` is set. Also block **GET exports** — `/export/fuel-entries.csv` and `/export/vehicles.csv` are GET routes that exfiltrate data; treat them like mutations for platform view.

```python
def block_platform_view_mutations(request: Request):
    session_data = getattr(request.state, "session_data", {})
    if not session_data.get("platform_view"):
        return
    path = request.url.path
    if request.method != "GET" or path.startswith("/export/"):
        raise InsufficientRoleException()  # or dedicated PlatformViewReadOnlyException
```

Scope the guard to **farm-scoped app routes** — do **not** block `/platform/*` POST (enter/exit view) or `/logout`.

Apply to all farm mutation POST routes: vehicles, fuel, maintenance, group settings, profile leave-group, billing checkout (when live), etc.

**UI affordances:** `group_page_capabilities()` in `app/services/membership.py` returns `can_edit=False` when the user has no `UserGroup` row — edit/delete buttons on list pages stay hidden in support view without template changes. Verify templates do not show standalone “Add” links outside `{% if can_edit %}`.

**Alternative:** Per-route `require_not_platform_view` dependency — explicit but easy to miss on new routes; prefer centralized middleware or a shared dependency on mutating handlers.

### 8.4 Routes (Phase 2)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/platform/farms/{group_id}/enter` | Set session to view farm; redirect `/dashboard` |
| `POST` | `/platform/exit-view` | Clear `platform_view`; redirect `/platform/farms` |

Both require CSRF token (existing global CSRF).

Audit:

- `platform.farm.enter` on enter
- `platform.farm.exit` on exit

### 8.5 UI banner

When `platform_view` is active, show a fixed banner in `base.html`:

> **Support view:** You are viewing **{farm name}** as platform operator. [Exit support view]

Style: high-visibility (e.g. amber bar). Never hide this state.

### 8.6 Role behaviour in support view

| Approach | Recommendation |
|----------|----------------|
| Treat as farm `reader` for display | ✅ Simplest — reuse existing templates |
| Treat as farm `admin` | ❌ Dangerous even if mutations blocked |
| Separate template branch | Only if reader view hides fields you need |

Use **reader-level visibility** for pages; platform admin already sees extra metadata on `/platform/farm/{id}`.

### 8.7 `StaleActiveGroupMiddleware` interaction

`StaleActiveGroupMiddleware` clears `active_group_id` in the cookie when membership is stale. When implementing platform view:

1. If `platform_view` is true and the target group exists (even without membership), **do not** set `request.state.clear_stale_active_group`.
2. When refreshing the cookie after enter/exit, pass through `platform_view` / `platform_view_group_id` via `app/services/sessions.py` → `app/auth.py`.

### 8.8 Phase 2 checklist

- [ ] Extend `create_session_cookie` / `set_session_cookie` with optional `platform_view` flags
- [ ] Update `refresh_session_cookie` and `start_user_session` in `app/services/sessions.py`
- [ ] Update `_attach_user_to_request` to bypass membership check when `platform_view` + valid group
- [ ] Update `require_role()` to treat platform view as **reader**
- [ ] Implement enter/exit routes
- [ ] Add read-only guard on mutating routes **and** `/export/*` GET routes
- [ ] Banner in `base.html` (use `request.state.session_data.get("platform_view")` or attach `request.state.platform_view`)
- [ ] Audit log entries for enter/exit
- [ ] Tests: non-operator cannot enter; operator can view dashboard without membership; operator cannot POST vehicle or download export CSV

---

## 9. Phase 3 – Production hardening

Before broad paid rollout:

### 9.1 Authentication hardening

- [ ] MFA on platform admin accounts (email accounts used in `PLATFORM_ADMIN_EMAILS`)
- [ ] Optional: separate subdomain `ops.yourdomain.com` pointing to same app
- [ ] Optional: IP allowlist for `/platform` routes
- [ ] Short session TTL for platform sessions (or force re-auth before enter-farm)

### 9.2 Billing integration

Once [STRIPE_BILLING.md](./STRIPE_BILLING.md) is implemented, extend farm list/detail with:

| Field | Source |
|-------|--------|
| Stripe customer ID | `group_subscriptions.stripe_customer_id` |
| Subscription status | `group_subscriptions.status` |
| Current period end | Stripe sync |
| Link to Stripe Dashboard | `https://dashboard.stripe.com/customers/{id}` |

### 9.3 Customer-initiated support access (optional, privacy-friendly)

Instead of permanent platform visibility into all farms:

- Farm admin clicks “Grant Tankly support access for 24 hours”
- Creates `SupportAccessGrant(group_id, expires_at, granted_by_user_id)`
- Platform admin can only `enter` farms with active grant **or** farms on allowlist for internal testing

Good for EU/GDPR-conscious customers. Not required for private beta.

### 9.4 Observability

- Structured log line on every `/platform` request: `platform_admin_action`, `admin_email`, `path`, `target_group_id`
- Sentry breadcrumb for platform routes (already have `SENTRY_DSN` in config)

---

## 10. Audit logging for platform actions

Existing helper (`app/audit.py`):

```python
log_event(db, group_id, user_id, action, entity_type, entity_id)
```

Farm audit log UI (`/settings/audit`) shows events **for that farm**. Platform actions should:

1. **Always log** with the **target** `group_id` when a farm is involved
2. Use a **`platform.*` action prefix** so farm admins see transparency (“Tankly support viewed your farm” — optional future UI)
3. Use `group_id=None` for global searches (user search with no specific farm)

### Suggested action names

| Action | When |
|--------|------|
| `platform.farm.list` | Opened farm list (optional — high volume; log at debug or sample) |
| `platform.farm.detail` | Viewed farm detail page |
| `platform.farm.enter` | Entered support view |
| `platform.farm.exit` | Exited support view |
| `platform.user.search` | Searched users |
| `platform.user.detail` | Viewed user detail |

**entity_type:** `"group"`, `"user"`, etc.  
**entity_id:** target id  
**user_id:** platform admin’s user id

Consider a dedicated **`PlatformAuditLog`** table later if farm audit log mixing becomes noisy. Not needed for Phase 1.

---

## 11. UI & templates

### Design principles

- **Visually distinct** from customer UI — avoid confusion (e.g. dark sidebar, “Operator” label)
- **Not linked** from customer nav (`base.html`) — operators bookmark `/platform/farms`
- Mobile-friendly but primarily desktop (support workflow)

### `platform_base.html`

- Header: “Tankly Operator”
- Nav links: Farms | Users | (Exit to app)
- No farm switcher from customer session unless in support view

### Farm list columns

| Column | Notes |
|--------|-------|
| Name | Link to detail |
| Members | Count |
| Vehicles | Count |
| Tier | free / pro / farm |
| Created | Relative + absolute date |
| Last activity | Or “No activity” |
| Status | Active / Deleted badge |

Filters: status, tier (once billing live), text search on name.

### Farm detail sections

1. **Overview** — metadata, tier, created by
2. **Members** — table with email, role, joined
3. **Usage** — vehicle/fuel/maintenance counts
4. **Recent activity** — audit log excerpt
5. **Actions** — “Enter support view” (Phase 2), link to Stripe (Phase 3)

---

## 12. Security rules

### Must have

1. **Allowlist only** — no self-service “become platform admin”
2. **Same auth stack** — platform routes use `get_current_user`, not a separate weak auth
3. **CSRF on all POST** — enter/exit support view included
4. **Audit every sensitive read** — at minimum farm detail, enter, user detail
5. **Read-only support view by default** — block mutations when `platform_view`
6. **No PII in logs** — log user ids and action names, not full emails in application logs (audit table is fine)

### Must not

1. **Do not** add platform admin as hidden member of every farm
2. **Do not** use a shared “god password” account
3. **Do not** bypass CSRF or rate limits on platform routes
4. **Do not** expose platform routes in sitemap / marketing

### Group scoping regression

[DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) lists cross-cutting security tests (`test_all_group_scoped_routes_check_membership`, `test_no_route_leaks_data_from_other_groups`) — these are requirements, not necessarily implemented as a single test module yet. Platform view **intentionally** bypasses membership for operators only — add **new** tests proving:

- Normal users still cannot access other groups
- Platform view cannot mutate
- Platform admin without `platform_view` session cannot open `/dashboard` for arbitrary group

---

## 13. Testing

Create `tests/test_platform_admin.py`.

### Access control

```
test_platform_routes_require_auth
test_platform_routes_require_platform_admin_email
test_non_allowlisted_user_gets_403_on_platform
test_empty_platform_admin_emails_disables_all_platform_access
```

### Phase 1 data

```
test_platform_farm_list_includes_all_groups_not_just_membership
test_platform_farm_list_shows_member_and_vehicle_counts
test_platform_farm_list_includes_soft_deleted_when_filtered
test_platform_farm_detail_shows_members_and_roles
test_platform_user_search_by_email
test_platform_user_detail_lists_farm_memberships
test_normal_user_cannot_access_other_group_via_platform_routes
```

### Phase 2 support view

```
test_platform_enter_sets_platform_view_cookie
test_platform_enter_allows_dashboard_without_membership
test_platform_view_blocks_vehicle_create_post
test_platform_view_blocks_group_settings_post
test_platform_view_blocks_export_csv_get
test_platform_view_cannot_access_settings_audit_get
test_platform_exit_clears_platform_view
test_platform_enter_logs_audit_event
```

### Fixtures

- `platform_admin_user` — email in `PLATFORM_ADMIN_EMAILS` (monkeypatch settings in test)
- `regular_user`, `other_farm` — user with no membership in target farm

---

## 14. Production checklist

### Before enabling in beta

- [ ] Set `PLATFORM_ADMIN_EMAILS` in Northflank secrets (your real operator email)
- [ ] Verify `/platform/farms` loads and shows beta farms
- [ ] Verify non-allowlisted account gets 403
- [ ] Confirm no link to `/platform` on public pages

### Before paid launch

- [ ] Phase 1 complete and tested
- [ ] Phase 2 if you expect support load
- [ ] MFA on operator email accounts
- [ ] Stripe fields visible on farm detail (if billing live)
- [ ] Runbook: how to look up customer by email, enter farm, exit
- [ ] Privacy policy mentions operator access for support (see legal review in PRODUCTION.md)

### Operator runbook (short)

1. Customer emails support → search `/platform/users?q=...`
2. Open farm detail → check members, tier, activity
3. If needed → “Enter support view” → reproduce on dashboard
4. Exit support view when done
5. Never change customer data from platform view in Phase 2 (read-only)

---

## 15. Alternatives & when to use them

| Approach | Pros | Cons | When |
|----------|------|------|------|
| **In-app `/platform` (recommended)** | Same auth, audit, view-as | Build effort | Default for sold SaaS |
| **Metabase / Retool on Postgres** | Fast charts, SQL | No view-as, separate auth | Supplement for analytics |
| **Direct SQL** | Full power | No audit, error-prone | Break-glass only |
| **Join farm via invite** | No code | Bad UX, shows as member | Never as primary |

**Recommended combo for Tankly:** in-app Phase 1 + optional Metabase later for revenue/churn charts.

---

## 16. Open decisions (for DECISION_LOG)

When implementation starts, record decisions such as:

### D-XXX: Platform admin via env allowlist (not DB role)

**Decision:** Grant platform admin via `PLATFORM_ADMIN_EMAILS`, not `User.is_platform_admin` in Phase 1.

**Rationale:** Solo operator, no redeploy-free grant needed yet, avoids accidental UI exposure.

**Trade-off:** Requires deploy to add/remove operators. Revisit DB flag when team grows.

### D-XXX: Platform support view is read-only

**Decision:** `platform_view` session may browse GET routes only; all mutations blocked.

**Rationale:** Minimises support accidents and preserves customer trust.

**Trade-off:** Cannot fix customer data from support view; operator must ask customer or use break-glass DB with separate process.

### D-XXX: Platform routes return 403 (not 404)

**Decision:** Non-operators receive forbidden response if they hit `/platform/*`.

**Rationale:** Consistent with existing `InsufficientRoleException` handling; simpler than dual 404/403 logic.

---

## 17. Implementation pitfalls (review checklist)

Use this when implementing — items that are easy to miss or were underspecified in early drafts:

| Pitfall | Detail |
|---------|--------|
| **`require_role` not updated** | Support view breaks on any route using `require_role` on GET — must synthesize reader role (§8.2). |
| **Export routes are GET** | `/export/*.csv` must be blocked in platform view (§8.3). |
| **`sessions.py` not updated** | All cookie refresh paths must preserve `platform_view` flags (§8.7). |
| **`StaleActiveGroupMiddleware` clears view** | Must skip stale clearing for valid platform view sessions (§8.7). |
| **No pagination elsewhere** | Do not assume an existing pagination helper (§7.4). |
| **`Group.created_by` has no relationship** | Join `User` manually in platform service queries. |
| **`/settings/group` in support view** | GET is allowed (no `require_role` on page load); operator sees member list and invite code — acceptable for support; mutations still POST-blocked. |
| **Audit log in app vs platform** | `/settings/audit` stays farm-admin-only; platform farm detail shows audit excerpt instead. |
| **Unauthenticated `/platform`** | Existing behaviour: redirect to `/login` with no `next=` param — optional enhancement to return to `/platform` after login. |
| **`.env.example` + `.env.beta.example`** | Document `PLATFORM_ADMIN_EMAILS` in both (project has both files). |
| **Config validation** | Add `@field_validator` to normalize `PLATFORM_ADMIN_EMAILS` (same pattern as `REGISTRATION_INVITE_CODE`). |
| **GDPR / Datenschutz** | Before paid launch, document operator access to customer data in `/datenschutz` (see [PRODUCTION.md](./PRODUCTION.md)). |
| **Phase 3 support grants** | Optional future restriction on **enter** — Phase 1–2 allowlisted operators can enter any farm; grants are additive policy later. |

---

## Appendix A – Development plan entry

Documented as **Phase 22** in [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md):

```markdown
## Phase 22: Platform Admin (Operator Dashboard)
```

(Full task list in DEVELOPMENT_PLAN.md — status: planned, not implemented.)

---

## Appendix B – File touch list (quick reference)

```
app/config.py                          # PLATFORM_ADMIN_EMAILS
app/dependencies.py                    # require_platform_admin, membership bypass
app/auth.py                            # platform_view cookie fields (Phase 2)
app/main.py                            # router + exception handler
app/services/platform_admin.py         # NEW
app/routes/platform.py                 # NEW
app/templates/platform_*.html          # NEW
app/templates/base.html                # support banner (Phase 2)
tests/test_platform_admin.py           # NEW
.docs/BETA_DEPLOY.md                   # document env var
.env.example                           # PLATFORM_ADMIN_EMAILS=
.env.beta.example                      # PLATFORM_ADMIN_EMAILS=
```

---

*Last updated: 2026-07-02 — reflects Tankly codebase (FastAPI, SQLAlchemy, group-scoped roles, `UserSession` table, no platform admin yet). §17 added after doc review against current routes/services.*
