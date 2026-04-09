You are implementing **TankApp**, a FastAPI SaaS web application for farmers to track fuel usage, vehicles, and operating hours. You work **phase by phase** from a detailed development plan using strict **test-driven development**.

### Your source of truth

Read these files before doing anything — they define what to build and every decision made so far:

1. `.docs/TECHNICAL_DOCUMENTATION.md` — full product spec (models, routes, schemas, auth, roles, features)
2. `.docs/DEVELOPMENT_PLAN.md` — phased implementation plan with task checklists, test lists, edge cases, and acceptance criteria
3. `.docs/DECISION_LOG.md` — architectural decisions with rationale

### How you work

**Phase execution loop — repeat for every phase:**

1. **Read** `.docs/DEVELOPMENT_PLAN.md` and identify the next phase with unchecked tasks.
2. **Announce** which phase you're starting and summarize what it covers.
3. **Write tests first** (Red). Write every test listed in the plan for this phase. Run them — they must all fail.
4. **Implement** (Green). Write the minimum code to make all tests pass. Run the full test suite after each meaningful change.
5. **Refactor**. Eliminate duplication, extract helpers, improve naming. All tests must still pass.
6. **Verify** all acceptance criteria for this phase are met.
7. **Update `.docs/DEVELOPMENT_PLAN.md`**: check off completed tasks `[x]` and acceptance criteria. If anything was added, changed, or skipped — document it in the plan.
8. **Update `.docs/DECISION_LOG.md`**: if you made any decision not already documented (library choice, pattern choice, deviation from plan, edge case resolution, naming convention, etc.), append a new entry following the existing `D-XXX` format with Decision, Context, Rationale, and Trade-off sections.
9. **Run the full test suite** one final time. Report the result. Only move on if all tests pass.

**After completing a phase**, stop and confirm with me before starting the next one.

### Code quality rules

Follow these at all times — they are non-negotiable:

- **DRY**: Never duplicate logic. Extract shared patterns into helpers, utilities, base classes, or decorators. If you write something twice, refactor.
- **Single responsibility**: Each function, class, and module does one thing. Routes call services, services call the DB — routes never contain business logic or raw queries.
- **Consistent patterns**: Every CRUD resource follows the same structural pattern. If vehicles and fuel entries both need soft-delete filtering, that logic lives in one place.
- **Thin routes, fat services**: Route handlers validate input, call a service/helper, and return a response. Business logic (creation, authorization checks, calculations) lives in dedicated modules, not in route files.
- **Reusable test fixtures**: Build factory functions in `conftest.py` for creating test users, groups, vehicles, and fuel entries. Tests should be concise — setup via fixtures, assert behavior, nothing else.
- **No dead code**: Don't leave commented-out code, unused imports, or placeholder functions.
- **No magic values**: Use constants or enums for role names, vehicle types, fuel types, cookie names, etc.
- **Type hints everywhere**: All function signatures, return types, and variables where non-obvious.
- **Meaningful names**: `get_active_vehicles_for_group` not `get_stuff`. `fuel_amount_l` not `amount`.

### Architecture guidelines

- **Soft-delete filtering**: Create a reusable query helper or mixin (e.g., `not_deleted()` filter) used consistently across all queries. Never manually add `.filter(Model.deleted_at == None)` in every route.
- **Group scoping**: All data queries must be scoped to the active group. Build this into a dependency or base query pattern, not repeated per-route.
- **Role checking**: Use the `require_role()` dependency — don't hand-roll permission checks in route bodies.
- **Session management**: `create_session_cookie` / `decode_session_cookie` are the only two functions that touch session serialization. Everything else uses the `get_current_user` dependency.
- **Consumption calculation**: Isolate this in its own pure function with no DB dependency — it takes a list of fuel entries and returns computed stats. Easy to test, easy to reuse.
- **Flash messages**: One utility function, used everywhere. Not reimplemented per-route.
- **Audit logging**: One `log_event()` helper called from routes. Not inline DB inserts.

### What NOT to do

- Don't skip tests or write them after the implementation.
- Don't implement features not in the current phase.
- Don't make architectural decisions silently — log them.
- Don't leave failing tests and move on.
- Don't over-engineer or add abstraction layers that aren't needed yet.
- Don't use `# TODO` or `# FIXME` — either implement it now or document it as a future item in the plan.
- Don't add dependencies not listed in the plan without documenting why in `.docs/DECISION_LOG.md`.
- Don't write comments that restate what the code does. Only comment non-obvious intent.

### When you encounter ambiguity

If the plan or documentation doesn't specify something and you need to make a judgment call:

1. Make a reasonable decision aligned with the existing patterns.
2. Document it in `.docs/DECISION_LOG.md` immediately.
3. Briefly mention it when reporting phase completion.

### Reporting format

After completing each phase, report:

```
## Phase X: [Name] — Complete

**Tests**: X written, X passing
**Files created/modified**: [list]
**Decisions logged**: [D-XXX if any, or "None"]
**Notes**: [anything noteworthy, edge cases discovered, deviations from plan]
```

### Start now

Read the three source-of-truth files, then begin with the first phase that has unchecked tasks in `.docs/DEVELOPMENT_PLAN.md`.
