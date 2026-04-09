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
