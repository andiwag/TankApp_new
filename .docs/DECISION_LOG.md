# TankApp – Decision Log

This document records architectural and design decisions made during planning, along with rationale and trade-offs.

---

## D-001: Authentication — Session-based with signed cookies

**Decision:** Use session-based authentication with signed cookies (via `itsdangerous`).

**Context:** The app is server-side rendered (Jinja2 templates, form POSTs). The question was whether session-based auth is optimal, and if so, how to store session data.

**Rationale:**
- Session-based auth is the natural fit for SSR apps with form submissions.
- JWT tokens add complexity that benefits SPAs/decoupled APIs — not relevant here.
- Signed cookies keep things stateless: no session table, no Redis, no server-side cleanup.
- Session payload is minimal (`user_id`, `active_group_id`), well within cookie size limits.

**Trade-off:** Sessions cannot be revoked server-side (e.g., force-logout a user). Acceptable for MVP. If needed later, migrate to a `Session` DB table.

---

## D-002: `usage_unit` — Derived from `vtype`, stored in DB

**Decision:** Auto-populate `usage_unit` from `vtype` during vehicle creation. Store it in the database but do not expose it as user input.

**Mapping:**
| vtype      | usage_unit |
|------------|------------|
| car        | km         |
| motorcycle | km         |
| tractor    | hours      |
| machine    | hours      |

**Rationale:** Storing it avoids repeated mapping logic in queries/templates. Auto-deriving it prevents inconsistency. The mapping is enforced at the application layer.

---

## D-003: `group_id` on FuelEntry — Intentional denormalization

**Decision:** Keep `group_id` on `FuelEntry` even though it can be derived via `Vehicle.group_id`.

**Rationale:**
- The most common query pattern is "all fuel entries for the active group." Direct filtering by `group_id` avoids a JOIN through `Vehicle` on every request.
- Worth the minor redundancy for simpler, faster queries.

**Constraint:** On creation, validate that `fuel_entry.group_id == vehicle.group_id`. This is enforced at the application layer.

---

## D-004: Consumption calculation logic

**Decision:** Calculate fuel consumption using consecutive usage readings per vehicle.

**Formula:**
- **km-based vehicles (car, motorcycle):** `fuel_amount_l / (current_reading - previous_reading) * 100` → result in **L/100km**
- **hours-based vehicles (tractor, machine):** `fuel_amount_l / (current_reading - previous_reading)` → result in **L/h**

**Rules:**
1. "Previous reading" = the most recent fuel entry for the same vehicle with a **lower** `usage_reading`, sorted by `usage_reading` (not by `entry_date`).
2. **First entry** for a vehicle: no consumption value (needs at least 2 data points).
3. **Out-of-order entries:** Sorting by `usage_reading` handles this correctly — chronological order of entry creation doesn't matter.
4. **Assumption:** All fills are **full tank fills**. Partial fills are not tracked in MVP. This is a documented limitation.

**Trade-off:** Partial fills will produce inaccurate consumption numbers. A `full_tank` boolean field could be added later to handle this.

---

## D-005: Soft delete for Users — Yes

**Decision:** Add `deleted_at` (nullable datetime) to the `User` model.

**Rationale:**
- `FuelEntry` references `user_id`. Hard-deleting a user would break referential integrity or cascade-delete their fuel entries, losing group data.
- Soft-deleted users' entries remain visible in group history.
- Enables future account reactivation if desired.

---

## D-006: AuditLog — Scoped to important events only

**Decision:** Implement audit logging for significant, low-frequency events. Do **not** log routine data entry.

**Logged events:**
| action              | entity_type | description                     |
|---------------------|-------------|---------------------------------|
| `user.register`     | user        | New account created             |
| `group.create`      | group       | New group created               |
| `group.delete`      | group       | Group soft-deleted               |
| `group.join`        | group       | User joined via invite code      |
| `group.leave`       | group       | User left a group               |
| `member.role_change`| user_group  | User role changed by admin       |
| `member.remove`     | user_group  | User removed from group by admin |
| `vehicle.create`    | vehicle     | New vehicle added                |
| `vehicle.delete`    | vehicle     | Vehicle soft-deleted             |

**Not logged:** `fuel_entry.*`, `vehicle.edit`, `user.login`, `user.logout`

**Rationale:** Logging every fuel entry edit would generate high-volume, low-value data. The important events are structural changes to the group, membership, and assets.

---

## D-007: Notes field on FuelEntry — Added

**Decision:** Add an optional `notes` field (string, nullable, max 500 chars) to `FuelEntry`.

**Rationale:** Farmers may want to record context like "partial fill," "borrowed from neighbor," or gas station name. Low-cost addition with high practical value.

---

## D-008: User `name` field — Added

**Decision:** Add a required `name` field (string) to `User`, provided during registration.

**Rationale:** In a collaborative group environment, users need to be identifiable by something friendlier than email. Displayed in group member lists, recent activity, and fuel entry attribution.

---

## D-009: Refactor — Consolidate enum/constant definitions into `app/enums.py`

**Decision:** Extract all domain enums (`VehicleType`, `FuelType`, `Role`, `UsageUnit`) and the `VTYPE_TO_USAGE_UNIT` mapping into a shared `app/enums.py` module. Both `models.py` and `schemas.py` import from this single source of truth.

**Context:** Previously, `models.py` defined raw tuples (`ROLE_VALUES`, `VTYPE_VALUES`, etc.) while `schemas.py` independently defined `VehicleType` and `FuelType` as Python `Enum` classes. The same domain values were maintained in two places with no link between them.

**Rationale:**
- Eliminates drift risk: adding a new vehicle type or fuel type now requires a change in exactly one place.
- The shared `Enum` classes are usable by both SQLAlchemy column definitions and Pydantic schemas.
- `VTYPE_TO_USAGE_UNIT` mapping is now typed with the enum classes, making it self-documenting.

**Trade-off:** Adds a new file (`app/enums.py`) and an import dependency from both `models.py` and `schemas.py`. Acceptable for a project of this size.

---

## D-010: Refactor — `NonEmptyStr` annotated type replaces repeated name validators

**Decision:** Replace the `_validate_non_empty` helper + per-schema `@model_validator` pattern with a reusable `NonEmptyStr = Annotated[str, AfterValidator(...)]` type. Schemas that need a non-empty, stripped string field now declare `name: NonEmptyStr` with no validator method.

**Context:** Three schemas (`UserCreate`, `VehicleCreate`, `GroupCreate`) each had an identical 4-line `@model_validator` that called `_validate_non_empty(self.name, "Name")`. This was correct but repetitive.

**Rationale:**
- Declaring `name: NonEmptyStr` is more declarative and Pydantic-idiomatic than a model validator for single-field validation.
- Removes ~12 lines of boilerplate across three schemas.
- The validation rule (strip + reject empty) is defined once and reusable for any future field.
- `UserCreate`'s model validator is kept but simplified to only handle password validation.

**Trade-off:** The error message is now generic ("Name must not be empty") rather than parameterized by field name. Acceptable because all current uses are for `name` fields.

---

## D-011: Refactor — Remove redundant SQLAlchemy column type arguments and nullable flags

**Decision:** Remove explicit SQLAlchemy type arguments (`Integer`, `String`, `DateTime`, `Date`) and `nullable` flags where they are already inferred from `Mapped[]` type annotations (SQLAlchemy 2.0+ feature).

**Context:** Every column specified both a `Mapped[T]` annotation and an explicit SA type argument (e.g., `Mapped[int] = mapped_column(Integer, ...)`). SQLAlchemy 2.0 infers `Integer` from `Mapped[int]`, `String` from `Mapped[str]`, `DateTime` from `Mapped[datetime]`, and `Date` from `Mapped[date]`. Similarly, `nullable=False` is inferred from `Mapped[T]` and `nullable=True` from `Mapped[T | None]`.

**Rationale:**
- Reduces visual noise, making relationships, constraints, and non-default options stand out.
- Follows SQLAlchemy 2.0 idiomatic style.
- Removed `Integer`, `DateTime`, `Date` from imports entirely.

**Kept explicit:** `Float` (SA 2.0 infers `Double` from `float`, which could cause migration confusion), `String(500)` (has a length constraint), and all `Enum(...)` columns (cannot be inferred).

**Trade-off:** Developers unfamiliar with SA 2.0 type inference may initially find the implicit typing surprising. The `Mapped[]` annotation is the single source of truth.

---

## D-012: Refactor — Use in-memory SQLite for tests

**Decision:** Change the test database URL from `sqlite:///./test.db` (file-based) to `sqlite://` (in-memory).

**Context:** The development plan specifies "In-memory SQLite test database" but the implementation used a file-based test database, leaving stale `test.db` files on disk.

**Rationale:**
- Aligns with the documented plan.
- Eliminates stale `test.db` files that could cause confusion or leftover state.
- Significantly faster: test suite dropped from ~10s to ~0.3s since in-memory SQLite avoids filesystem I/O.
- No risk of parallel test runs interfering with each other through a shared file.

**Trade-off:** In-memory databases cannot be inspected after test failure for debugging. If needed, temporarily switch back to file-based for investigation.

---

## D-013: Refactor — Move `test_health_endpoint` from `test_config.py` to `test_main.py`

**Decision:** Move the health endpoint integration test out of `test_config.py` into a new `tests/test_main.py` file.

**Context:** `test_config.py` contained two configuration unit tests and one HTTP endpoint test (`test_health_endpoint`). The endpoint test has nothing to do with configuration; it tests a route defined in `main.py`.

**Rationale:**
- Test files should mirror the module they test. Config tests belong in `test_config.py`, route tests belong in a file matching their source module.
- As the test suite grows to ~251 tests, clear file-to-module correspondence prevents confusion.
- The `pytest` import in `test_config.py` was only needed for the `@pytest.mark.asyncio` decorator on the misplaced test, so it was removed as well.

**Trade-off:** None significant. Adds one small file.

---

## D-014: Refactor — Move dependency override into `setup_database` fixture

**Decision:** Move the `app.dependency_overrides[get_db] = override_get_db` statement from module-level into the session-scoped `setup_database` fixture, with `app.dependency_overrides.clear()` in the teardown.

**Context:** The override was applied as a module-level side effect at import time of `conftest.py`. This mutated global app state implicitly, making it non-obvious when and why the override was active.

**Rationale:**
- The override is now explicit: it's set up in the fixture and cleaned up after the test session.
- Makes the test lifecycle self-documenting — setup and teardown are visible in one place.
- Prevents potential issues if conftest is imported from unexpected contexts.

**Trade-off:** None. The `setup_database` fixture is `scope="session"` and `autouse=True`, so the override is still applied before any test runs.

---

## D-015: Refactor — Move model imports to top of `conftest.py`

**Decision:** Move `from app.models import User, Group, Vehicle` to the top-level imports in `conftest.py`, removing the lazy `from app.models import ...` statements inside each factory fixture's inner function.

**Context:** The three factory fixtures (`create_test_user`, `create_test_group`, `create_test_vehicle`) each had a `from app.models import X` inside their inner `_create` function. This is unconventional for test code and obscures which models `conftest.py` depends on.

**Rationale:**
- Top-level imports are the Python convention and make dependencies visible at a glance.
- There is no circular import risk since test modules are never imported by app code.
- Reduces 3 lines of boilerplate inside fixture factories.

**Trade-off:** None.

---

## D-016: Refactor — Replace deprecated `datetime.utcnow` with `datetime.now(timezone.utc)`

**Decision:** Replace all uses of `datetime.utcnow` (deprecated since Python 3.12) with `datetime.now(timezone.utc)` via a module-level `_utcnow()` helper in `models.py`. Test code was also updated to use `datetime.now(timezone.utc)`.

**Context:** `datetime.utcnow()` returns a naive datetime (no timezone info) and is deprecated in Python 3.12+ per PEP 615. The project uses Python 3.10 but should be forward-compatible.

**Rationale:**
- `datetime.now(timezone.utc)` returns a timezone-aware datetime, which is unambiguous and correct.
- A `_utcnow()` helper avoids repeating `lambda: datetime.now(timezone.utc)` across 10 column definitions — SQLAlchemy's `default=` and `onupdate=` require a callable reference, not a call expression.
- Prevents deprecation warnings when upgrading to Python 3.12+.

**Trade-off:** Timestamps are now timezone-aware (`tzinfo=UTC`) rather than naive. Existing naive timestamps in the database will still work with SQLite (which stores text), but on PostgreSQL a column type migration from `TIMESTAMP` to `TIMESTAMP WITH TIME ZONE` may be needed in the future.

---

## D-017: Auth exception handling — Custom exceptions with FastAPI exception handlers

**Decision:** Define `NotAuthenticatedException`, `NoActiveGroupException`, and `InsufficientRoleException` in `dependencies.py`. Register exception handlers in `main.py` that return `RedirectResponse` (for auth/group failures) or `Response(403)` (for role failures).

**Context:** FastAPI dependencies can't return HTTP responses directly — they must either return a value or raise. For an SSR app, auth failures should redirect to login, not return JSON errors.

**Rationale:**
- Custom exceptions keep dependency logic clean (raise, don't return).
- Exception handlers centralize redirect/error behavior in `main.py`.
- Different exception types map to different recovery actions: login redirect vs. group selection redirect vs. 403 Forbidden.

**Trade-off:** Adds three exception classes and three handlers. Simpler alternatives (HTTPException with status 303) don't support clean redirect semantics in SSR apps.

---

## D-018: Session data sharing — `request.state.session_data`

**Decision:** `get_current_user` stores the decoded session dict on `request.state.session_data`. Downstream dependencies (`get_active_group`, `require_role`) read from `request.state` instead of re-decoding the cookie.

**Context:** Both `require_role` and `get_active_group` need `active_group_id` from the session. Re-decoding the signed cookie in each dependency would be redundant.

**Rationale:**
- Avoids duplicate cryptographic verification per request.
- `request.state` is the standard Starlette mechanism for per-request data sharing.
- `get_current_user` is a sub-dependency of both `get_active_group` and `require_role`, so it always runs first.

**Trade-off:** Creates an implicit coupling — downstream dependencies depend on `get_current_user` having populated `request.state`. This is enforced via `Depends(get_current_user)` in their signatures, making the ordering explicit.

---

## D-019: Test infrastructure — `StaticPool` for in-memory SQLite

**Decision:** Add `poolclass=StaticPool` to the test engine configuration.

**Context:** Phase 3 introduced integration tests that create data in one DB session (test fixtures) and read it from another (route handler via `override_get_db`). With in-memory SQLite, each new connection creates a separate database by default.

**Rationale:**
- `StaticPool` ensures all sessions share the same underlying connection and therefore the same in-memory database.
- Without it, data created by test fixtures would be invisible to route handlers, causing false test failures.
- This is the standard SQLAlchemy recommendation for testing with in-memory SQLite.

**Trade-off:** All sessions share one connection, so concurrent writes could theoretically conflict. Not an issue for sequential test execution.

---

## D-020: Minimal templates for Phase 3 — Full styling deferred to Phase 6

**Decision:** Create minimal `login.html` and `register.html` templates in Phase 3 with basic HTML forms (no Tailwind, no Alpine.js, no base template inheritance). Phase 6 will add the full base template layout and styling.

**Context:** Phase 3 needs functional login/register pages to test auth routes. Phase 6 is dedicated to the base template, Tailwind CSS, Alpine.js, and responsive layout.

**Rationale:**
- Keeps Phase 3 focused on auth logic, not UI.
- Templates have the correct form fields and error display, enabling meaningful integration tests.
- Phase 6 will refactor these templates to extend `base.html` with full styling.

**Trade-off:** Templates are temporarily unstyled. Acceptable since Phase 6 immediately follows the auth-related phases.

---

## D-021: Password reset tokens — Password-hash fingerprint for single-use enforcement

**Decision:** Embed a prefix of the user's current `password_hash` (first 16 characters) in the password reset token payload. On token verification, compare this fingerprint against the user's current hash.

**Context:** The development plan requires that used tokens cannot be reused (`test_reset_password_used_token_cannot_reuse`). Options considered:
1. Store issued tokens in a database table and mark them as used.
2. Embed a password-hash fingerprint in the token so it self-invalidates after a password change.

**Rationale:**
- Option 2 is stateless — no new database table, no cleanup of expired tokens.
- When the user resets their password, the hash changes, and any token containing the old fingerprint automatically fails verification.
- This also protects against the edge case where a user changes their password through another method (e.g., profile settings) after requesting a reset.
- Uses `itsdangerous.URLSafeTimedSerializer` with a dedicated `"password-reset"` salt to separate reset tokens from session cookies.

**Trade-off:** The token payload includes a password-hash prefix, which leaks a small amount of information about the hash format. The 16-character prefix (`$2b$12$...salt`) is not security-sensitive since bcrypt's algorithm identifier and cost factor are public knowledge. If paranoia increases, hash the prefix with SHA-256 before embedding.

---

## D-022: Password reset email delivery — Development logging, production deferred

**Decision:** Implement a `_deliver_reset_token` helper in `app/routes/auth.py` that logs the reset link in development mode. Production email delivery via `fastapi-mail` is deferred (function body is a no-op for production).

**Context:** The plan calls for configuring `fastapi-mail`, but actual SMTP credentials and a mail server are not available during local development. The tests mock `_deliver_reset_token` to capture and verify the generated token.

**Rationale:**
- Keeps Phase 4 focused on reset logic, not email infrastructure.
- The helper is easily testable via `unittest.mock.patch`.
- When production email is needed, only `_deliver_reset_token` needs updating — no route logic changes.

**Trade-off:** `fastapi-mail` is listed in `requirements.txt` but not yet imported or configured. This is acceptable — it will be integrated when production deployment is set up.

---

## D-023: Refactor — Extract `set_session_cookie` into `app/auth.py`

**Decision:** Move the session-cookie-setting logic out of `app/routes/auth.py` (where it was a private `_set_session_cookie` helper) into a public `set_session_cookie(response, user_id, active_group_id)` function in `app/auth.py`. Both `app/routes/auth.py` and `app/routes/groups.py` import from this single location.

**Context:** Phase 5 introduced `app/routes/groups.py`, which needs to set session cookies after creating, joining, switching, leaving, and deleting groups. Duplicating the 6-line cookie-setting helper across two route modules would violate DRY.

**Rationale:**
- `app/auth.py` already owns session cookie creation (`create_session_cookie`) and decoding — adding the response-setting step is a natural extension.
- The function duck-types on `response` (calls `.set_cookie()`), so it doesn't import any FastAPI types, keeping `auth.py` framework-light.
- Both route modules now call one function with consistent cookie flags (`httponly`, `samesite`).

**Trade-off:** `app/auth.py` now implicitly depends on the response object having a `.set_cookie()` method. This is standard across Starlette/FastAPI response types.

---

## D-024: Refactor — Extract `first_validation_error_message` into `app/schemas.py`

**Decision:** Move the Pydantic `ValidationError` → user-friendly string helper from a private function in `app/routes/auth.py` to a public `first_validation_error_message(exc)` function in `app/schemas.py`. Both route modules import from `schemas.py`.

**Context:** Phase 5 group routes need to display schema validation errors (e.g., empty group name) the same way auth routes do. The helper was previously private to the auth route module.

**Rationale:**
- `schemas.py` defines the schemas and already imports `ValidationError` — it's the natural home for error message extraction.
- Prevents the two route modules from each maintaining their own copy of identical logic.

**Trade-off:** None significant. Adds one public function to `schemas.py`.

---

## D-025: Invite code generation — `FARM-XXXXX` format with collision retry

**Decision:** Generate invite codes in the format `FARM-XXXXX` where `X` is a random uppercase alphanumeric character (A-Z, 0-9). Use `secrets.choice` for cryptographic randomness. On collision (code already exists in DB), retry up to 10 times.

**Context:** The technical documentation specifies the invite code format `FARM-82KD9`. The code space is 36^5 ≈ 60 million unique codes, making collisions extremely rare in practice.

**Rationale:**
- `secrets` module ensures codes are not predictable.
- The 5-character suffix provides a good balance between readability and uniqueness.
- Retry logic handles the (extremely unlikely) collision case defensively.
- The format is human-readable and easy to share verbally.

**Trade-off:** 10 retries is arbitrary but sufficient given the collision probability. If the system ever reaches millions of groups, the retry count or code length could be increased.

---

## D-026: Group error handling — Re-render template with error vs. HTTP status codes

**Decision:** Group routes use two error response patterns:
1. **Form/business-logic errors** (empty name, invalid invite code, already a member, sole admin leaving): re-render `groups.html` with a 200 status and an `error` context variable, following the same pattern used by auth routes.
2. **Authorization errors** (not a member, non-admin attempting delete): return 403 Forbidden.

**Context:** In an SSR app, error responses need to be user-visible. The question was whether to redirect with flash messages, return HTTP error codes, or re-render with inline errors.

**Rationale:**
- Re-rendering with error context is consistent with how login/register handle validation failures — no flash message system needed yet (Phase 6).
- 403 for authorization failures is standard and doesn't need a rendered page (the exception handler in `main.py` handles it).
- The `_render_groups_with_error` helper re-queries the user's groups to populate the template, avoiding stale data.

**Trade-off:** Re-rendering requires an additional DB query for the groups list. This is negligible for the expected group count per user.

---

## D-027: Refactor — Shared `auth_cookie` and `create_test_user_group` test fixtures

**Decision:** Move the `auth_cookie` fixture from `tests/test_auth.py` to `tests/conftest.py` and add a new `create_test_user_group` fixture.

**Context:** Phase 5 tests need to authenticate users via session cookies and create user-group memberships — the same operations that Phase 3 tests already performed. The `auth_cookie` fixture was defined locally in `test_auth.py`.

**Rationale:**
- `conftest.py` is the standard location for shared pytest fixtures.
- `create_test_user_group` eliminates repetitive `db.add(UserGroup(...)); db.commit()` boilerplate across Phase 5 tests.
- Avoids duplicating the fixture definition across test modules.

**Trade-off:** None. pytest auto-discovers conftest fixtures for all test files in the same directory.

---

## D-028: `Form("")` default for group name — Accept empty strings for schema validation

**Decision:** Use `name: str = Form("")` instead of `name: str = Form(...)` in the `POST /groups/create` route, allowing empty strings to reach the route handler where `GroupCreate` schema validation rejects them with a clear error message.

**Context:** FastAPI's `Form(...)` (required) returns a 422 Unprocessable Entity for empty form fields before the route handler executes. For an SSR app, a 422 JSON error response is not user-friendly — the user should see the groups page with an inline error message.

**Rationale:**
- Lets the `GroupCreate` schema's `NonEmptyStr` validator handle the validation with a human-readable error.
- The route handler catches the `ValidationError` and re-renders the template with the error, consistent with how other validation errors are handled.

**Trade-off:** The field is technically "optional" at the FastAPI level, but the schema enforces non-empty. This is the correct pattern for SSR form validation where we want to control the error UX.

---

## D-029: Flash messages — Cookie-based with middleware auto-injection

**Decision:** Implement flash messages using a JSON cookie (`tankapp_flash`) read by a `FlashMiddleware` that populates `request.state.flash` and auto-clears the cookie after display. Flash is set via `set_flash(response, message, category)`.

**Context:** The app needed a way to display one-time messages after redirects (e.g., "Group created", "Logged out"). Options were: query parameters, session-based storage, or cookies.

**Rationale:**
- Cookie-based flash survives redirects without server-side session storage, consistent with the stateless architecture (D-001).
- Middleware initializes `request.state.flash` to `None` on every request, so templates can safely access it without guard clauses.
- The middleware also initializes `request.state.user` and `request.state.active_group` to `None`, providing a clean default for unauthenticated pages.
- `set_flash()` is a single helper function used by any route — no per-route boilerplate.

**Trade-off:** Flash data is stored in a plain JSON cookie (not signed). Since it only contains display messages (not security-sensitive data), this is acceptable. Cookie `max_age=60` limits exposure.

---

## D-030: Nav context — Populate `request.state.user` and `request.state.active_group` in dependencies

**Decision:** Extend `get_current_user` to also set `request.state.user` and resolve the active group (via PK lookup) into `request.state.active_group`. The `FlashMiddleware` initializes both to `None` so unauthenticated pages have safe defaults.

**Context:** The base template needs user name and active group name in the navigation bar. Every authenticated page would need to pass these explicitly to the template context, violating DRY.

**Rationale:**
- `request.state` is the standard Starlette mechanism for per-request data sharing.
- Since `get_current_user` already runs for every authenticated route, adding the active group lookup there avoids extra dependencies or context-building helpers.
- Templates access `request.state.user` and `request.state.active_group` directly — no need for route handlers to pass nav context.

**Trade-off:** `get_current_user` now performs an additional DB query (active group PK lookup) on every authenticated request. This is a cheap query and eliminates duplication across all authenticated routes.

---

## D-031: Refactor — Simplify `get_active_group` to use `request.state`

**Decision:** Simplify `get_active_group` to read from `request.state.active_group` (set by `get_current_user`) instead of re-querying the database. Remove the `db: Session` parameter since the query is no longer needed.

**Context:** After D-030, `get_current_user` already resolves the active group and stores it on `request.state`. The original `get_active_group` performed the same PK lookup redundantly.

**Rationale:**
- Eliminates a duplicate query for the same group object within a single request.
- Simplifies the dependency to a 3-line function.
- `get_active_group` still depends on `get_current_user` (via `Depends`), so the resolution order is guaranteed.

**Trade-off:** `get_active_group` now implicitly depends on `get_current_user` having populated `request.state.active_group`. This coupling is enforced via `Depends(get_current_user)` in the function signature.

---

## D-032: Dashboard statistics — service module and soft-delete rules

**Decision:** Implement dashboard aggregates in `app/services/dashboard.py` (`get_dashboard_context`). Vehicle counts exclude soft-deleted vehicles. Fuel entry counts, total liters, and the recent list exclude soft-deleted fuel entries and additionally require a non-deleted vehicle (JOIN), so entries tied to a soft-deleted vehicle do not appear in totals or recent activity. Recent rows are ordered by `entry_date` descending, then `FuelEntry.id` descending, limited to 10.

**Context:** Phase 7 needs group-scoped stats without duplicating filter logic in the route handler.

**Rationale:**
- Keeps the route thin and centralizes query rules for reuse and testing.
- Joining `Vehicle` ensures dashboard numbers stay consistent when a vehicle is hidden but orphan rows could theoretically exist.
- Ordering by `entry_date` matches user expectations for “recent” activity; tie-breaking by `id` makes order deterministic.

**Trade-off:** Slightly more complex query than filtering `FuelEntry` alone; acceptable for correct semantics.

---

## D-033: Vehicles CRUD — duplicate names, 404 for cross-group IDs, `VehicleUpdate` rules

**Decision:** (1) Allow multiple vehicles with the same display name within one group — no uniqueness constraint beyond the primary key. (2) When a user requests edit or delete for a vehicle ID that belongs to another group or is soft-deleted, return **404 Not Found** (not 403) so existence of that ID is not leaked across groups. (3) `VehicleUpdate` keeps optional `name` and `fuel_type`; at least one must be present after validation. Optional `name` is normalized in a field validator (strip; all-whitespace becomes `None`). HTML edit forms submit both fields.

**Context:** Phase 8 implements vehicle list/create/edit/delete with contributor-or-higher for mutations and admin-only soft delete. The plan’s Phase 8 “Authorization” tests reuse names from the groups phase (`test_create_group_any_authenticated_user`, `test_delete_group_requires_admin`) but assert vehicle route behavior.

**Rationale:**
- Duplicate names match real farms (e.g. two tractors with the same model name); uniqueness is unnecessary for MVP.
- 404 for wrong-group or soft-deleted vehicle IDs satisfies “denied” tests while avoiding cross-group information disclosure.
- Centralized vehicle logic lives in `app/services/vehicles.py`; routes validate with `VehicleCreate` / `VehicleUpdate` and delegate to the service.

**Trade-off:** Users distinguish similar names via type, fuel, and usage unit in the list until internal codes or nicknames exist.

---

## D-034: Fuel entries CRUD — align with vehicles (service layer, 404, roles, invalid vehicle UX)

**Decision:** Implement fuel entry listing and mutations in `app/services/fuel_entries.py`. Routes use `FuelEntryCreate` / `FuelEntryUpdate` with `first_validation_error_message` on validation failure. Cross-group or missing fuel entry IDs for edit/delete return **404**. Creating an entry with a `vehicle_id` that is not an active vehicle in the active group (including soft-deleted vehicles) re-renders the create form with **200** and a **red** inline error (same pattern as schema failures), not 404 — the user may have a stale form. Contributors and admins may create and edit; only **admins** may soft-delete fuel entries. `FuelEntryUpdate` requires at least one field and rejects future `entry_date` values (same rule as create). Navigation includes a **Fuel** link next to **Vehicles** when an active group is set.

**Context:** Phase 9 mirrors Phase 8 structure while enforcing D-003 (`group_id` on `FuelEntry` matches the chosen vehicle’s group) and DRY query helpers via reuse of `vehicle_service.get_active_vehicle_in_group` for create.

**Rationale:** Keeps routes thin, matches established SSR error UX, and avoids leaking whether an ID exists in another group for edit/delete (404), while keeping form-based create failures user-recoverable.

**Trade-off:** Invalid `vehicle_id` on POST returns a rendered error page instead of 404; acceptable for HTML forms and clearer for end users.

---

## D-035: Refactor — Fuel entry updates apply all set fields; reuse vehicle list query

**Decision:** (1) Implement `apply_fuel_entry_update` by assigning every attribute in `FuelEntryUpdate.model_dump(exclude_unset=True)` so an explicit `notes=None` clears the notes column (the previous `if data.notes is not None` branch prevented clearing). (2) Remove `list_vehicles_for_fuel_dropdown` and use `vehicles.list_vehicles_for_group` for the fuel create form vehicle dropdown.

**Context:** Post-implementation review found duplicated vehicle-query logic and a real bug when saving an edit with an empty notes field.

**Rationale:** `exclude_unset=True` matches Pydantic’s intended partial-update semantics and fixes note clearing. A single list function for active vehicles avoids two sources of truth for soft-delete and ordering rules.

**Trade-off:** If a future caller constructs `FuelEntryUpdate()` with no fields set, `require_at_least_one_field` still applies; `model_dump(exclude_unset=True)` can be empty and only `updated_at` would change — unlikely for current routes.

---

## D-036: Refactor — `group_page_capabilities` + fuel list aligned with dashboard vehicle scope

**Decision:** (1) Extract duplicated `UserGroup` + `ROLE_HIERARCHY` logic from `vehicles_page_context` and `fuel_entries_page_context` into `app/services/membership.py` as `group_page_capabilities(db, user, group_id)`. (2) Join `Vehicle` on fuel entry list and single-entry lookups; require `Vehicle.deleted_at` null so entries tied to soft-deleted vehicles are omitted from the fuel list and return 404 for edit/delete, matching dashboard statistics scope (D-032).

**Context:** Codebase review found copy-pasted capability checks; fuel list previously showed rows whose vehicle was already soft-deleted, inconsistent with dashboard aggregates.

**Rationale:** One implementation of contributor/admin affordances; consistent UX and queries for “active” fuel activity in a group.

**Trade-off:** Slightly more complex queries (inner join on `vehicles`).
