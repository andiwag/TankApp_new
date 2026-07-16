# Tankly — AI coding instructions

Instructions for GitHub Copilot, Cursor, and other AI assistants working in this repository.

**Product:** Tankly (`app/branding.py`) — FastAPI SaaS for farms to track fuel, vehicles, maintenance, and operating hours. Server-rendered Jinja2 UI, PostgreSQL in production, SQLite locally.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy · Alembic · pytest · httpx · ruff

### Which file to use

| File | Role |
|------|------|
| **This file** (`.github/copilot-instructions.md`) | Canonical workflow — TDD, architecture, testing, git, reporting |
| `.cursor/rules/tankly-development.mdc` | Cursor always-on pointer to this file |
| `.prompts/AGENT_PROMPT.md` | Optional phase kickoff only — current phase table, spec links, “start now” |

Do not duplicate workflow rules in `AGENT_PROMPT.md` or Cursor rules.

---

## 1. Source of truth (read before coding)

| Priority | Document | Use for |
|----------|----------|---------|
| 1 | `.docs/DEVELOPMENT_PLAN.md` | Phases, task checklists, test names, acceptance criteria |
| 2 | `.docs/TECHNICAL_DOCUMENTATION.md` | Models, routes, auth, roles, architecture |
| 3 | `.docs/DECISION_LOG.md` | Existing decisions (`D-XXX`) — do not contradict |
| 4 | Feature specs | e.g. `.docs/PLATFORM_ADMIN.md` (Phase 22), `.docs/STRIPE_BILLING.md` (Phase 23) |

**Plan status:** Phases 0–23 complete. Go-live checklist: `.docs/STRIPE_GO_LIVE.md`.

**Do not re-implement completed phases** or add scope outside the current task without user approval.

---

## 2. Non-negotiable: test-driven development

Every behavior change follows **Red → Green → Refactor**. Tests are written **before** implementation, not after.

### Red — write failing tests first

1. Read the phase or feature spec and list the behaviors to cover.
2. Add tests in `tests/test_<area>.py` (new file if needed).
3. Name tests clearly: `test_<what>_<expected_outcome>` (e.g. `test_platform_routes_require_platform_admin_email`).
4. Use existing fixtures from `tests/conftest.py` — do not reinvent auth/DB setup.
5. Run the new tests and **confirm they fail** for the right reason (missing feature, not typos).

```powershell
python -m pytest tests/test_platform_admin.py -q
```

### Green — minimum implementation

1. Write the **smallest** code that makes the new tests pass.
2. Re-run the **new tests**, then the **full suite** after each meaningful change.
3. Do not leave failing tests and continue.

```powershell
python -m pytest -q
```

### Refactor — clean up with tests green

1. Remove duplication, improve names, align with existing patterns.
2. Run the full suite again — behavior must not change.

### When tests are not listed in the plan

Derive them from acceptance criteria and spec sections. At minimum cover:

- Happy path
- Authorization / access control (403, redirect to login)
- Group scoping / cross-tenant isolation (no data leaks)
- Soft-delete exclusion where applicable
- CSRF on POST/PUT/DELETE (use `CsrfAsyncClient` via `client` fixture)
- Config edge cases (empty env, invalid input)

---

## 3. Coding workflow

Use this loop for **every task** — full phase or single feature slice.

### Before writing code

1. **Understand scope** — which phase, spec section, or user request?
2. **Read relevant docs** — plan, technical doc, feature spec, related `D-XXX` entries.
3. **Scan existing code** — match patterns in the nearest similar route/service/test file.
4. **Announce** — briefly state what you are building and which tests you will write first.

### Implementation order

```
Spec / acceptance criteria
        ↓
   Failing tests (Red)
        ↓
   Config / models / migrations (if needed)
        ↓
   Service layer (business logic, queries)
        ↓
   Routes (thin handlers)
        ↓
   Templates (if UI)
        ↓
   All tests green (Green)
        ↓
   Refactor + lint
        ↓
   Update docs + report
```

### After implementation

1. **Lint:** `ruff check app tests` and `ruff format app tests` (CI runs format check).
2. **Test:** full suite must pass (`python -m pytest -q`).
3. **Update `.docs/DEVELOPMENT_PLAN.md`** — check off completed tasks and acceptance criteria when finishing a phase or plan item.
4. **Update `.docs/DECISION_LOG.md`** — append `D-XXX` for any new architectural choice (Decision, Context, Rationale, Trade-off — match existing entries).
5. **Report** using the format in §8 (use the actual pytest count from `python -m pytest -q`; do not hardcode a number).

### Phase boundaries

When completing a **full development-plan phase**, stop and confirm with the user before starting the next phase unless they asked to continue.

For **partial work** (e.g. “Phase 22 Phase 1 only”), still follow TDD and update the plan checkboxes for what you actually finished.

---

## 4. Architecture rules

Match existing conventions — read neighbors before adding code.

| Layer | Responsibility |
|-------|----------------|
| `app/routes/` | HTTP: parse input, call service, return response/template. No business logic. |
| `app/services/` | Business logic, DB queries, aggregations. |
| `app/models.py` | SQLAlchemy ORM only. |
| `app/schemas.py` | Pydantic validation for forms/API. |
| `app/dependencies.py` | Auth, active group, `require_role()`. |
| `app/templates/` | Jinja2 HTML. |

**Hard rules:**

- **Group scoping** — farm data queries scoped to active group via dependencies/services.
- **Soft deletes** — filter `deleted_at IS NULL` in services consistently.
- **Roles** — use `require_role()`; never hand-roll permission checks in route bodies.
- **Sessions** — signed cookie + `UserSession` row; helpers in `app/auth.py` and `app/services/sessions.py`.
- **Audit** — `log_event()` from routes/services, not raw `AuditLog` inserts.
- **Flash messages** — `set_flash()` in `app/flash.py` + `FlashMiddleware`.
- **Consumption math** — pure functions in `app/services/consumption.py` (no DB).
- **Thin routes, fat services** — routes never contain raw SQL or multi-step business logic.
- **DRY** — extract shared logic; reuse `conftest.py` factories.
- **Type hints** on all function signatures.
- **Meaningful names** — e.g. `get_active_vehicles_for_group`, not `get_stuff`.
- **No magic strings** — use `app/enums.py`, `app/branding.py`, constants.
- **No dead code** — no commented-out blocks, unused imports, or `# TODO` / `# FIXME`.
- **Comments** — only for non-obvious business rules; never restate the code.
- **Dependencies** — do not add packages without documenting why in `DECISION_LOG.md`.

---

## 5. Testing conventions

**Framework:** pytest + pytest-asyncio + httpx `AsyncClient`.

**Fixtures** (`tests/conftest.py`):

| Fixture | Purpose |
|---------|---------|
| `client` | Async HTTP client with CSRF on unsafe methods |
| `db` | DB session (tables cleaned after each test) |
| `create_test_user` | User factory |
| `create_test_group` | Group/farm factory |
| `create_test_user_group` | Membership + role |
| `create_test_vehicle` / `create_test_fuel_entry` | Domain factories |
| `auth_cookie` | Set session cookie on client |
| `auth_group` | One-liner authenticated user + group + cookie |

**Patterns:**

- Use `auth_group(role="admin")` for authenticated route tests.
- For config tests, monkeypatch `settings` or env vars — restore after test.
- Assert status codes **and** response body / DB state where relevant.
- Security tests from the plan (CSRF, auth required, group isolation) apply across phases.

**CI:** GitHub Actions runs ruff + pytest on Postgres with `--cov-fail-under=75`. Local SQLite runs are fine for dev; CI uses Postgres.

---

## 6. Commands reference

```powershell
# Activate venv (Windows)
.\.venv\Scripts\Activate.ps1

# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
python -m pytest -q

# Run one file or test
python -m pytest tests/test_auth.py -q
python -m pytest tests/test_auth.py::test_login_success -q

# Lint + format
ruff check app tests
ruff format app tests

# Local dev server
uvicorn app.main:app --reload
```

**Migrations:** use Alembic when models change (`alembic revision --autogenerate`, review, `alembic upgrade head`).

---

## 7. What NOT to do

- Do **not** implement first and add tests later.
- Do **not** skip running tests or ignore failures.
- Do **not** expand scope beyond the current task/phase without user approval.
- Do **not** make silent architectural decisions — log them in `DECISION_LOG.md`.
- Do **not** commit unless the user explicitly asks.
- Do **not** push to remote unless the user explicitly asks.
- Do **not** over-engineer (no premature abstractions, no extra features “while you’re here”).
- Do **not** grant platform operator access via farm `admin` role — see `.docs/PLATFORM_ADMIN.md`.

---

## 8. Reporting format

After completing a task or phase:

```markdown
## [Phase X / Feature name] — Complete

**Tests:** N new, all passing (full suite: M/M)
**Files created/modified:** [list]
**Decisions logged:** D-XXX or None
**Notes:** [deviations, edge cases, follow-ups]
```

---

## 9. Handling ambiguity

1. Prefer the choice that matches existing patterns in the codebase.
2. Document the decision in `.docs/DECISION_LOG.md` immediately.
3. Mention it in the completion report.

---

## 10. Git and PRs

- **Commits:** only when the user requests. Use concise messages focused on *why*.
- **PRs:** use `gh` when asked; include summary and test plan.
- Never force-push to `main`/`master`.

---

## Quick checklist (every change)

- [ ] Read spec + existing similar code
- [ ] Wrote failing tests first (Red)
- [ ] Implemented minimum code (Green)
- [ ] Full test suite passes
- [ ] `ruff check` / `ruff format` clean
- [ ] Updated `DEVELOPMENT_PLAN.md` / `DECISION_LOG.md` if applicable
- [ ] Reported results to user
