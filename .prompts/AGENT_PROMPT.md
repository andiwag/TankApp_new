You are implementing **Tankly** (`app/branding.py`), a FastAPI SaaS web application for farmers to track fuel, vehicles, maintenance, and operating hours. The GitHub folder may still be named `TankApp_new`. You work **phase by phase** from the development plan using strict **test-driven development**.

### Current plan status (check `.docs/DEVELOPMENT_PLAN.md` for details)

| Phases | Status |
|--------|--------|
| **0–16** | Original MVP — complete |
| **17–21** | Post-MVP (maintenance, analytics/export/cost, audit UI, sessions & production hardening, marketing/beta gate) — complete |
| **22** | Platform admin (`/platform`) — **planned**, spec in `.docs/PLATFORM_ADMIN.md` |
| **23** | Stripe billing — **planned**, spec in `.docs/STRIPE_BILLING.md` |

**Next work:** Phase **22** unless the user directs otherwise. Do not re-implement completed phases.

### Your source of truth

Read these before doing anything:

1. `.docs/TECHNICAL_DOCUMENTATION.md` — product spec (models, routes, auth, roles, features)
2. `.docs/DEVELOPMENT_PLAN.md` — phases, task checklists, tests, acceptance criteria
3. `.docs/DECISION_LOG.md` — architectural decisions (`D-XXX`)

**Also read when relevant:**

- `.docs/PLATFORM_ADMIN.md` — Phase 22 operator dashboard (not implemented yet)
- `.docs/STRIPE_BILLING.md` — Phase 23 billing (not implemented yet)
- `.docs/BETA_DEPLOY.md` / `.docs/PRODUCTION.md` — deployment and env vars

### How you work

**Phase execution loop — repeat for every phase:**

1. **Read** `.docs/DEVELOPMENT_PLAN.md` and identify the next phase with unchecked tasks.
2. **Announce** which phase you're starting and summarize what it covers.
3. **Write tests first** (Red). Write every test listed in the plan for this phase. Run them — they must all fail.
4. **Implement** (Green). Write the minimum code to make all tests pass. Run the full test suite after each meaningful change (~371 tests today).
5. **Refactor**. Eliminate duplication, extract helpers, improve naming. All tests must still pass.
6. **Verify** all acceptance criteria for this phase are met.
7. **Update `.docs/DEVELOPMENT_PLAN.md`**: check off completed tasks `[x]` and acceptance criteria. Document anything added, changed, or skipped.
8. **Update `.docs/DECISION_LOG.md`**: append new `D-XXX` entries for any decision not already documented (Decision, Context, Rationale, Trade-off).
9. **Run the full test suite** one final time. Report the result. Only move on if all tests pass.

**After completing a phase**, stop and confirm with the user before starting the next one.

### Code quality rules

Follow these at all times — they are non-negotiable:

- **DRY**: Never duplicate logic. Extract shared patterns into helpers, utilities, base classes, or decorators.
- **Single responsibility**: Routes call services, services call the DB — routes never contain business logic or raw queries.
- **Consistent patterns**: Match existing CRUD, soft-delete, and group-scoping patterns (vehicles, fuel, maintenance).
- **Thin routes, fat services**: Route handlers validate input, call a service, return a response.
- **Reusable test fixtures**: Use `conftest.py` factories (`create_test_user`, `create_test_group`, etc.).
- **No dead code**: No commented-out code, unused imports, or placeholders.
- **No magic values**: Use enums/constants from `app/enums.py`, `app/branding.py`, etc.
- **Type hints everywhere** on function signatures and non-obvious variables.
- **Meaningful names**: `get_active_vehicles_for_group` not `get_stuff`.

### Architecture guidelines

- **Soft-delete filtering**: Filter `deleted_at IS NULL` consistently in services — not ad hoc in every route.
- **Group scoping**: All farm data queries scoped to the active group via dependencies/services.
- **Role checking**: Use `require_role()` — don't hand-roll permission checks in route bodies.
- **Sessions**: Signed cookie (`session_id`, `user_id`, `active_group_id`) + `UserSession` row (D-046). Use `get_current_user`; cookie helpers live in `app/auth.py` and `app/services/sessions.py`.
- **Consumption calculation**: Pure functions in `app/services/consumption.py` — no DB inside.
- **Flash messages**: `set_flash()` + middleware — not reimplemented per route.
- **Audit logging**: `log_event()` from routes — not inline inserts.
- **Platform admin (Phase 22)**: Separate from farm `admin` role — see `.docs/PLATFORM_ADMIN.md` (env allowlist, `/platform/*`, read-only support view).

### What NOT to do

- Don't skip tests or write them after implementation.
- Don't implement features outside the current phase without user approval.
- Don't make architectural decisions silently — log them in `DECISION_LOG.md`.
- Don't leave failing tests and move on.
- Don't over-engineer.
- Don't use `# TODO` / `# FIXME` — implement or document in the plan.
- Don't add dependencies without documenting why in `DECISION_LOG.md`.
- Don't write comments that restate the code.

### When you encounter ambiguity

1. Decide aligned with existing patterns.
2. Document in `.docs/DECISION_LOG.md` immediately.
3. Mention it when reporting phase completion.

### Reporting format

After completing each phase:

```
## Phase X: [Name] — Complete

**Tests**: X written, X passing (full suite: N/N)
**Files created/modified**: [list]
**Decisions logged**: [D-XXX if any, or "None"]
**Notes**: [edge cases, deviations from plan]
```

### Start now

Read the source-of-truth files, then begin with the **first phase that has unchecked tasks** in `.docs/DEVELOPMENT_PLAN.md` (currently **Phase 22: Platform Admin** unless the user says otherwise).
