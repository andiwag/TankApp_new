# Tankly – Test-Driven Development Plan

Phased plan for **Tankly** (product name; GitHub folder may still be `TankApp_new`). Phases **0–16** = original MVP (complete). **17–21** = post-MVP delivery (complete). **22** = complete. **23–28** = planned — see linked guides.

## Documentation index

| Document | Purpose |
|----------|---------|
| [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) | Product spec, models, routes, auth |
| [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) | This file — phases, tests, acceptance criteria |
| [DECISION_LOG.md](./DECISION_LOG.md) | Architectural decisions (`D-XXX`) |
| [BETA_DEPLOY.md](./BETA_DEPLOY.md) | Private beta on Northflank ($0) |
| [PRODUCTION.md](./PRODUCTION.md) | Production hardening & deploy details |
| [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md) | **Planned** operator dashboard (`/platform`) |
| [STRIPE_BILLING.md](./STRIPE_BILLING.md) | **Planned** Stripe billing per group |
| [TANK_INVENTORY_AND_ADBLUE.md](./TANK_INVENTORY_AND_ADBLUE.md) | **Planned** farm tank inventory, fill sources, AdBlue |

All development follows a strict **Red → Green → Refactor** TDD cycle:
1. **Red:** Write a failing test that defines expected behavior.
2. **Green:** Write the minimum code to make the test pass.
3. **Refactor:** Clean up without changing behavior; all tests must still pass.

Tests use **pytest** + **pytest-asyncio** + **httpx** (for async FastAPI TestClient).

---

## Phase 0: Project Setup & Test Infrastructure

### Tasks
- [x] Initialize Python project with virtual environment
- [x] Create `requirements.txt` with pinned dependencies
- [x] Create `.env.example` with all required environment variables
- [x] Create `app/__init__.py`, `app/main.py` (minimal FastAPI app)
- [x] Create `app/config.py` (settings via pydantic-settings / python-dotenv)
- [x] Set up pytest configuration (`pyproject.toml` or `pytest.ini`)
- [x] Create `tests/` directory structure:
  ```
  tests/
    __init__.py
    conftest.py          (shared fixtures: test client, test DB, test user factory)
    test_config.py
    test_models.py
    test_auth.py
    test_groups.py
    test_vehicles.py
    test_fuel_entries.py
    test_dashboard.py
    test_summary.py
    test_profile.py
    test_audit_log.py
  ```
- [x] Create `conftest.py` with:
  - In-memory SQLite test database
  - Test client fixture (async httpx.AsyncClient)
  - Database session override
  - Factory fixtures: `create_test_user`, `create_test_group`, `create_test_vehicle`
- [x] Verify: `pytest` runs with 0 tests collected, no errors

### Acceptance Criteria
- [x] `pytest` runs cleanly on an empty test suite
- [x] Test DB is isolated (in-memory SQLite, created/destroyed per test)
- [x] Test client can make requests to the FastAPI app
- [x] `.env.example` documents all required variables

---

## Phase 1: Database & Models

### Tasks
- [x] Create `app/database.py` — engine, session factory, Base
- [x] Create `app/models.py` — all ORM models:
  - `User` (id, email, name, password_hash, created_at, deleted_at)
  - `Group` (id, name, invite_code, subscription_tier, created_by, created_at, deleted_at)
  - `UserGroup` (user_id, group_id, role, joined_at) — composite PK
  - `Vehicle` (id, group_id, name, vtype, usage_unit, fuel_type, created_at, updated_at, deleted_at)
  - `FuelEntry` (id, vehicle_id, group_id, user_id, fuel_amount_l, usage_reading, notes, entry_date, created_at, updated_at, deleted_at)
  - `AuditLog` (id, group_id, user_id, action, entity_type, entity_id, created_at)
- [x] Set up Alembic (`alembic init`, configure `env.py`)
- [x] Generate initial migration
- [x] Apply migration to dev DB

### Tests (write FIRST)

**Model creation & constraints:**
```
test_create_user_valid
test_create_user_duplicate_email_fails
test_user_email_is_required
test_user_name_is_required
test_user_soft_delete_sets_deleted_at

test_create_group_valid
test_group_invite_code_unique
test_group_soft_delete

test_create_user_group_valid
test_user_group_composite_pk_prevents_duplicates
test_user_group_role_enum_values

test_create_vehicle_valid
test_vehicle_usage_unit_derived_from_vtype_car
test_vehicle_usage_unit_derived_from_vtype_tractor
test_vehicle_usage_unit_derived_from_vtype_motorcycle
test_vehicle_usage_unit_derived_from_vtype_machine
test_vehicle_belongs_to_group
test_vehicle_soft_delete

test_create_fuel_entry_valid
test_fuel_entry_group_id_matches_vehicle_group_id
test_fuel_entry_notes_optional
test_fuel_entry_soft_delete

test_create_audit_log_valid
```

**Relationship tests:**
```
test_user_has_many_groups_through_user_group
test_group_has_many_users_through_user_group
test_group_has_many_vehicles
test_vehicle_has_many_fuel_entries
test_fuel_entry_belongs_to_user
```

### Edge Cases
- Duplicate email on User creation → IntegrityError
- Duplicate (user_id, group_id) on UserGroup → IntegrityError
- Invalid vtype value → validation error
- Invalid role value → validation error
- FuelEntry with negative fuel_amount_l → validation error
- FuelEntry with negative usage_reading → validation error

### Acceptance Criteria
- [x] All 6 models create, read, and soft-delete correctly
- [x] Relationships and foreign keys are enforced
- [x] `usage_unit` is auto-derived from `vtype`
- [x] Alembic migration applies and rolls back cleanly
- [x] All model tests pass

---

## Phase 2: Pydantic Schemas

### Tasks
- [x] Create `app/schemas.py` with all request/response schemas:
  - `UserCreate` (email, name, password, password_confirm)
  - `UserLogin` (email, password)
  - `UserUpdate` (name optional, email optional)
  - `PasswordChange` (current_password, new_password, new_password_confirm)
  - `VehicleCreate` (name, vtype, fuel_type)
  - `VehicleUpdate` (name optional, fuel_type optional)
  - `FuelEntryCreate` (vehicle_id, fuel_amount_l, usage_reading, entry_date, notes optional)
  - `FuelEntryUpdate` (fuel_amount_l optional, usage_reading optional, entry_date optional, notes optional)
  - `GroupCreate` (name)
  - `JoinGroup` (invite_code)
  - `PasswordResetRequest` (email)
  - `PasswordResetConfirm` (token, new_password, new_password_confirm)

### Tests (write FIRST)
```
test_user_create_valid
test_user_create_password_mismatch_fails
test_user_create_short_password_fails
test_user_create_invalid_email_fails
test_user_create_empty_name_fails

test_vehicle_create_valid
test_vehicle_create_invalid_vtype_fails
test_vehicle_create_invalid_fuel_type_fails

test_fuel_entry_create_valid
test_fuel_entry_create_negative_amount_fails
test_fuel_entry_create_negative_reading_fails
test_fuel_entry_create_zero_amount_fails
test_fuel_entry_create_future_date_fails

test_group_create_valid
test_group_create_empty_name_fails

test_password_change_mismatch_fails
test_password_reset_confirm_mismatch_fails
```

### Edge Cases
- Password < 8 characters
- Password confirmation doesn't match
- Email without valid format
- fuel_amount_l = 0 or negative
- usage_reading negative
- entry_date in the future
- Empty vehicle name
- vtype not in allowed enum
- fuel_type not in allowed enum

### Acceptance Criteria
- [x] All schemas validate correct input
- [x] All schemas reject invalid input with clear error messages
- [x] All schema tests pass

---

## Phase 3: Authentication (Register, Login, Logout)

### Tasks
- [x] Create `app/auth.py`:
  - `hash_password(plain)` → bcrypt hash
  - `verify_password(plain, hashed)` → bool
  - `create_session_cookie(user_id, active_group_id, session_id=...)` → signed cookie value
  - `decode_session_cookie(cookie_value)` → dict or None
- [x] Create `app/services/sessions.py` for DB-backed session creation, lookup, expiry, and revocation
- [x] Create `app/dependencies.py`:
  - `get_current_user(request)` → User or redirect to login
  - `get_active_group(request)` → Group or redirect to group selection
  - `require_role(min_role)` → dependency factory
- [x] Create `app/routes/auth.py`:
  - `GET /login` — render login form
  - `POST /login` — authenticate, set cookie, redirect
  - `GET /register` — render registration form
  - `POST /register` — create user, set cookie, redirect
  - `POST /logout` — revoke session, clear cookie, redirect to login

### Tests (write FIRST)

**Unit tests (auth.py):**
```
test_hash_password_returns_bcrypt_hash
test_verify_password_correct
test_verify_password_incorrect
test_create_session_cookie_returns_string
test_decode_session_cookie_valid
test_decode_session_cookie_tampered_returns_none
test_decode_session_cookie_expired_returns_none
```

**Integration tests (routes):**
```
test_get_login_page_returns_200
test_get_register_page_returns_200

test_register_valid_creates_user_and_redirects
test_register_duplicate_email_shows_error
test_register_password_mismatch_shows_error
test_register_sets_session_cookie

test_login_valid_redirects_to_dashboard
test_login_invalid_email_shows_error
test_login_invalid_password_shows_error
test_login_sets_session_cookie
test_login_soft_deleted_user_fails

test_logout_clears_cookie
test_logout_redirects_to_login

test_protected_route_without_session_redirects_to_login
test_protected_route_with_valid_session_succeeds
test_protected_route_with_tampered_cookie_redirects
```

**Dependency tests:**
```
test_get_current_user_with_valid_session
test_get_current_user_without_session_redirects
test_require_role_admin_allows_admin
test_require_role_admin_blocks_contributor
test_require_role_admin_blocks_reader
test_require_role_contributor_allows_admin
test_require_role_contributor_allows_contributor
test_require_role_contributor_blocks_reader
```

### Edge Cases
- Register with email that already exists (case-insensitive)
- Login with correct email but wrong password
- Login with non-existent email
- Tampered session cookie
- Missing session cookie
- Login with soft-deleted user account
- Register with leading/trailing whitespace in email

### Acceptance Criteria
- [x] Users can register with email, name, and password
- [x] Users can log in and receive a session cookie
- [x] Users can log out and cookie is cleared
- [x] Protected routes redirect unauthenticated users to login
- [x] Passwords are stored as bcrypt hashes, never plaintext
- [x] All auth tests pass

---

## Phase 4: Password Reset

### Tasks
- [x] Create password reset token generation (itsdangerous TimedSerializer)
- [x] Create `app/routes/auth.py` additions:
  - `GET /forgot-password` — render form
  - `POST /forgot-password` — generate token, send email (or log in dev)
  - `GET /reset-password/{token}` — render reset form
  - `POST /reset-password/{token}` — validate token, update password
- [x] Configure `fastapi-mail` (or mock in development)

### Tests (write FIRST)
```
test_get_forgot_password_page_returns_200
test_forgot_password_existing_email_succeeds
test_forgot_password_nonexistent_email_succeeds_silently
test_forgot_password_generates_token

test_get_reset_password_page_valid_token_returns_200
test_get_reset_password_page_invalid_token_shows_error
test_get_reset_password_page_expired_token_shows_error

test_reset_password_valid_token_changes_password
test_reset_password_invalid_token_fails
test_reset_password_expired_token_fails
test_reset_password_password_mismatch_shows_error
test_reset_password_used_token_cannot_reuse
```

### Edge Cases
- Token expiration (e.g., 1 hour)
- Non-existent email → still return success (prevent email enumeration)
- Token reuse after password change
- Malformed token
- Soft-deleted user requesting reset

### Acceptance Criteria
- [x] Users can request a password reset link
- [x] Valid tokens allow password change
- [x] Expired/invalid tokens are rejected
- [x] Non-existent emails don't leak information
- [x] All password reset tests pass

---

## Phase 5: Group System

### Tasks
- [x] Create `app/routes/groups.py`:
  - `GET /groups` — list user's groups, show create/join forms
  - `POST /groups/create` — create group, set user as admin
  - `POST /groups/join` — join via invite code, set as contributor
  - `POST /groups/switch/{id}` — switch active group in session
  - `POST /groups/leave/{id}` — leave group (admin can't leave if sole admin)
  - `POST /groups/delete/{id}` — soft-delete group (admin only)
- [x] Generate invite codes (format: `FARM-XXXXX`, alphanumeric)
- [x] After registration: redirect to group selection if no groups exist

### Tests (write FIRST)

**Group CRUD:**
```
test_create_group_valid
test_create_group_sets_creator_as_admin
test_create_group_generates_invite_code
test_create_group_empty_name_fails

test_join_group_valid_code
test_join_group_invalid_code_fails
test_join_group_sets_role_contributor
test_join_group_already_member_shows_error
test_join_group_deleted_group_fails

test_switch_group_valid
test_switch_group_not_member_fails
test_switch_group_updates_session

test_leave_group_as_contributor
test_leave_group_as_admin_with_other_admins
test_leave_group_as_sole_admin_fails
test_leave_group_not_member_fails

test_delete_group_as_admin
test_delete_group_as_contributor_fails
test_delete_group_as_reader_fails
test_delete_group_soft_deletes
```

**Authorization:**
```
test_group_routes_require_authentication
test_create_group_any_authenticated_user
test_delete_group_requires_admin
```

### Edge Cases
- Creating a group when already in multiple groups
- Joining a group you're already a member of
- Leaving a group as the sole admin (must be prevented)
- Switching to a group you're not a member of
- Joining a soft-deleted group
- Invite code collision during generation (retry logic)
- User with no groups → forced to group selection page

### Acceptance Criteria
- [x] Users can create groups and become admin
- [x] Users can join groups via invite code
- [x] Users can switch between groups
- [x] Users can leave groups (with sole-admin protection)
- [x] Admins can soft-delete groups
- [x] Group context is maintained in session
- [x] All group tests pass

---

## Phase 6: Base Template & Layout

### Tasks
- [x] Create `app/templates/base.html`:
  - Tailwind CSS, Alpine.js, Chart.js (self-hosted under `/static/vendor/`)
  - Navigation bar (responsive, mobile hamburger menu)
  - Flash message display area
  - Active group indicator
  - User name display
  - Logout button
  - Footer
- [x] Create `app/templates/login.html`
- [x] Create `app/templates/register.html`
- [x] Create `app/templates/groups.html`
- [x] Set up static file serving in FastAPI
- [x] Implement flash message system (via cookie or query param)

### Tests (write FIRST)
```
test_base_template_includes_tailwind
test_base_template_includes_alpine
test_login_page_has_email_and_password_fields
test_register_page_has_name_email_password_fields
test_authenticated_page_shows_user_name
test_authenticated_page_shows_active_group
test_authenticated_page_has_logout_button
test_flash_message_displayed_after_redirect
```

### Acceptance Criteria
- [x] All pages inherit from base template
- [x] Navigation is responsive (mobile-friendly)
- [x] Flash messages appear after actions (success/error)
- [x] Active group name visible in nav
- [x] All template tests pass

---

## Phase 7: Dashboard

### Tasks
- [x] Create `app/routes/dashboard.py`:
  - `GET /dashboard` — render dashboard with statistics
- [x] Create `app/templates/dashboard.html`:
  - Total vehicles count
  - Total fuel entries count
  - Total fuel liters
  - Recent fuel entries (last 5–10)
- [x] Dashboard scoped to active group

### Tests (write FIRST)
```
test_dashboard_requires_auth
test_dashboard_requires_active_group
test_dashboard_shows_vehicle_count
test_dashboard_shows_entry_count
test_dashboard_shows_total_liters
test_dashboard_shows_recent_entries
test_dashboard_scoped_to_active_group
test_dashboard_excludes_soft_deleted_vehicles
test_dashboard_excludes_soft_deleted_entries
test_dashboard_empty_group_shows_zeros
```

### Edge Cases
- Group with no vehicles or entries (show zeros, not errors)
- Soft-deleted vehicles/entries excluded from counts
- User switches groups → dashboard reflects new group data

### Acceptance Criteria
- [x] Dashboard displays correct counts for active group
- [x] Soft-deleted records are excluded
- [x] Empty state is handled gracefully
- [x] All dashboard tests pass

---

## Phase 8: Vehicles CRUD

### Tasks
- [x] Create `app/routes/vehicles.py`:
  - `GET /vehicles` — list vehicles (active group, exclude soft-deleted)
  - `GET /vehicles/new` — render create form (admin, contributor)
  - `POST /vehicles/new` — create vehicle (auto-set usage_unit)
  - `GET /vehicles/{id}/edit` — render edit form (admin, contributor)
  - `POST /vehicles/{id}/edit` — update vehicle
  - `POST /vehicles/{id}/delete` — soft-delete vehicle (admin only)
- [x] Create `app/templates/vehicles.html`
- [x] Create `app/templates/vehicle_form.html`

### Tests (write FIRST)

**List:**
```
test_list_vehicles_returns_200
test_list_vehicles_scoped_to_active_group
test_list_vehicles_excludes_soft_deleted
test_list_vehicles_requires_auth
```

**Create:**
```
test_create_vehicle_valid_car
test_create_vehicle_valid_tractor
test_create_vehicle_sets_usage_unit_km_for_car
test_create_vehicle_sets_usage_unit_km_for_motorcycle
test_create_vehicle_sets_usage_unit_hours_for_tractor
test_create_vehicle_sets_usage_unit_hours_for_machine
test_create_vehicle_sets_group_id_from_session
test_create_vehicle_invalid_vtype_fails
test_create_vehicle_empty_name_fails
test_create_vehicle_requires_contributor_role
test_create_vehicle_reader_denied
```

**Edit:**
```
test_edit_vehicle_valid
test_edit_vehicle_name_only
test_edit_vehicle_fuel_type_only
test_edit_vehicle_wrong_group_denied
test_edit_vehicle_requires_contributor_role
test_edit_vehicle_reader_denied
test_edit_vehicle_not_found_404
test_edit_soft_deleted_vehicle_404
```

**Delete:**
```
test_delete_vehicle_as_admin
test_delete_vehicle_as_contributor_denied
test_delete_vehicle_as_reader_denied
test_delete_vehicle_sets_deleted_at
test_delete_vehicle_wrong_group_denied
test_delete_vehicle_not_found_404
```

### Edge Cases
- Editing a vehicle from another group → 403/404
- Deleting a vehicle with existing fuel entries (soft delete keeps entries)
- Creating vehicle with very long name
- Duplicate vehicle names within same group (allowed or not?)

### Acceptance Criteria
- [x] CRUD operations work for vehicles within active group
- [x] `usage_unit` is auto-set from `vtype`, not editable
- [x] Soft delete preserves data, hides from list
- [x] Role-based access is enforced
- [x] Cross-group access is denied
- [x] All vehicle tests pass

---

## Phase 9: Fuel Entries CRUD

### Tasks
- [x] Create `app/routes/fuel_entries.py`:
  - `GET /fuel` — list fuel entries (active group, exclude soft-deleted)
  - `GET /fuel/new` — render create form with vehicle dropdown (admin, contributor)
  - `POST /fuel/new` — create fuel entry
  - `GET /fuel/{id}/edit` — render edit form (admin, contributor)
  - `POST /fuel/{id}/edit` — update fuel entry
  - `POST /fuel/{id}/delete` — soft-delete fuel entry (admin only)
- [x] Create `app/templates/fuel_entries.html`
- [x] Create `app/templates/fuel_entry_form.html`
- [x] Validate `group_id` matches `vehicle.group_id` on creation
- [x] Vehicle dropdown only shows non-deleted vehicles from active group

### Tests (write FIRST)

**List:**
```
test_list_fuel_entries_returns_200
test_list_fuel_entries_scoped_to_active_group
test_list_fuel_entries_excludes_soft_deleted
test_list_fuel_entries_shows_vehicle_name
test_list_fuel_entries_shows_user_name
test_list_fuel_entries_requires_auth
```

**Create:**
```
test_create_fuel_entry_valid
test_create_fuel_entry_sets_group_id_from_vehicle
test_create_fuel_entry_sets_user_id_from_session
test_create_fuel_entry_with_notes
test_create_fuel_entry_without_notes
test_create_fuel_entry_vehicle_from_other_group_denied
test_create_fuel_entry_soft_deleted_vehicle_denied
test_create_fuel_entry_negative_amount_fails
test_create_fuel_entry_zero_amount_fails
test_create_fuel_entry_negative_reading_fails
test_create_fuel_entry_future_date_fails
test_create_fuel_entry_requires_contributor_role
test_create_fuel_entry_reader_denied
```

**Edit:**
```
test_edit_fuel_entry_valid
test_edit_fuel_entry_partial_update
test_edit_fuel_entry_wrong_group_denied
test_edit_fuel_entry_requires_contributor_role
test_edit_fuel_entry_not_found_404
test_edit_soft_deleted_fuel_entry_404
```

**Delete:**
```
test_delete_fuel_entry_as_admin
test_delete_fuel_entry_as_contributor_denied
test_delete_fuel_entry_as_reader_denied
test_delete_fuel_entry_sets_deleted_at
test_delete_fuel_entry_wrong_group_denied
```

### Edge Cases
- Creating entry for a vehicle belonging to another group
- Creating entry for a soft-deleted vehicle
- Usage reading lower than a previous entry (valid — could be odometer reset or correction)
- Very large fuel amounts (e.g., 10,000L — plausible for farm tanks)
- entry_date in the future
- Notes field at max length (500 chars)
- Notes field with special characters / HTML (must be escaped)

### Acceptance Criteria
- [x] CRUD operations work for fuel entries within active group
- [x] `group_id` is auto-set to match the vehicle's group
- [x] `user_id` is auto-set from the session
- [x] Validation prevents invalid data
- [x] Cross-group access is denied
- [x] Role-based access is enforced
- [x] All fuel entry tests pass

---

## Phase 10: User Profile Management

### Tasks
- [x] Create `app/routes/profile.py`:
  - `GET /profile` — render profile page
  - `POST /profile` — update name and/or email
  - `POST /profile/change-password` — change password
- [x] Create `app/templates/profile.html`

### Tests (write FIRST)
```
test_get_profile_page_returns_200
test_get_profile_shows_current_name_and_email
test_update_profile_name
test_update_profile_email
test_update_profile_duplicate_email_fails
test_update_profile_requires_auth

test_change_password_valid
test_change_password_wrong_current_password_fails
test_change_password_mismatch_confirmation_fails
test_change_password_short_password_fails
test_change_password_requires_auth
```

### Edge Cases
- Changing email to one already in use
- Changing email to same email (no-op, success)
- Empty name
- Password change with wrong current password

### Acceptance Criteria
- [x] Users can view and update their profile
- [x] Users can change their password
- [x] Email uniqueness is enforced
- [x] All profile tests pass

---

## Phase 11: Summary & Statistics

### Tasks
- [x] Create `app/routes/summary.py`:
  - `GET /summary` — render summary page with statistics
- [x] Create `app/templates/summary.html`
- [x] Implement consumption calculation logic (see D-004)
- [x] Display:
  - Fuel per vehicle (total liters, entry count)
  - Total fuel per month (last 12 months)
  - Consumption averages per vehicle (L/100km or L/h)

### Tests (write FIRST)

**Fuel per vehicle:**
```
test_summary_fuel_per_vehicle_total_liters
test_summary_fuel_per_vehicle_entry_count
test_summary_fuel_per_vehicle_excludes_soft_deleted_entries
test_summary_fuel_per_vehicle_excludes_soft_deleted_vehicles
test_summary_fuel_per_vehicle_scoped_to_active_group
```

**Monthly totals:**
```
test_summary_monthly_totals_last_12_months
test_summary_monthly_totals_empty_months_show_zero
test_summary_monthly_totals_excludes_soft_deleted
```

**Consumption averages:**
```
test_consumption_car_two_entries_calculates_l_per_100km
test_consumption_tractor_two_entries_calculates_l_per_hour
test_consumption_single_entry_no_result
test_consumption_three_entries_calculates_average
test_consumption_excludes_soft_deleted_entries
test_consumption_sorts_by_usage_reading_not_date
test_consumption_handles_large_gap_in_readings
```

**Page:**
```
test_summary_requires_auth
test_summary_requires_active_group
test_summary_empty_group_shows_no_data_message
```

### Edge Cases
- Vehicle with only 1 fuel entry → no consumption value, just total liters
- Vehicle with 0 entries → excluded from consumption, shows 0 liters
- All entries soft-deleted → show empty state
- Very high consumption value (possible data entry error) → display anyway
- Entries spanning year boundary in monthly totals
- Group with no vehicles at all

### Acceptance Criteria
- [x] Summary shows fuel totals per vehicle
- [x] Summary shows monthly fuel totals
- [x] Consumption averages are calculated correctly per D-004
- [x] Empty states handled gracefully
- [x] All summary tests pass

---

## Phase 12: Group Settings

### Tasks
- [x] Create `app/routes/group_settings.py`:
  - `GET /settings/group` — render group settings page
  - `POST /settings/group/regenerate-code` — regenerate invite code (admin)
  - `POST /settings/group/members/{user_id}/role` — change member role (admin)
  - `POST /settings/group/members/{user_id}/remove` — remove member (admin)
- [x] Create `app/templates/group_settings.html`:
  - Invite code display + copy button
  - Member list with roles
  - Role change dropdown (admin only)
  - Remove member button (admin only)
  - Danger zone: delete group button

### Tests (write FIRST)
```
test_group_settings_page_returns_200
test_group_settings_requires_auth
test_group_settings_shows_invite_code
test_group_settings_shows_members_with_roles
test_group_settings_admin_sees_role_controls
test_group_settings_contributor_cannot_see_role_controls
test_group_settings_reader_cannot_see_role_controls

test_regenerate_invite_code_as_admin
test_regenerate_invite_code_as_contributor_denied
test_regenerate_invite_code_changes_code

test_change_member_role_as_admin
test_change_member_role_as_contributor_denied
test_change_member_role_cannot_demote_self
test_change_member_role_valid_roles_only
test_change_member_role_member_not_in_group_404

test_remove_member_as_admin
test_remove_member_as_contributor_denied
test_remove_member_cannot_remove_self
test_remove_member_not_in_group_404
```

### Edge Cases
- Admin demoting themselves (prevent if sole admin)
- Admin removing themselves (prevent — use "leave group" instead)
- Changing role of a user not in the group
- Regenerating code while others have the old code (old code stops working)
- Last admin tries to change own role to contributor

### Acceptance Criteria
- [x] Group settings page shows invite code and members
- [x] Admins can regenerate invite codes
- [x] Admins can change member roles
- [x] Admins can remove members
- [x] Self-demotion/removal is prevented for sole admins
- [x] All group settings tests pass

---

## Phase 13: Audit Logging

### Tasks
- [x] Create `app/audit.py`:
  - `log_event(db, group_id, user_id, action, entity_type, entity_id)` helper function
- [x] Integrate audit logging into relevant route handlers (see D-006 for event list)
- [x] Optional audit display skipped at Phase 13 — **UI added in Phase 19** (`GET /settings/audit`)

### Tests (write FIRST)
```
test_audit_log_created_on_user_register
test_audit_log_created_on_group_create
test_audit_log_created_on_group_delete
test_audit_log_created_on_group_join
test_audit_log_created_on_group_leave
test_audit_log_created_on_member_role_change
test_audit_log_created_on_member_remove
test_audit_log_created_on_vehicle_create
test_audit_log_created_on_vehicle_delete
test_audit_log_not_created_on_fuel_entry_create
test_audit_log_not_created_on_vehicle_edit
test_audit_log_stores_correct_entity_type_and_id
test_audit_log_stores_correct_user_id
```

### Acceptance Criteria
- [x] Important events are logged per D-006
- [x] Routine operations are NOT logged
- [x] Audit log entries have correct metadata
- [x] All audit tests pass

---

## Phase 14: CSRF Protection

### Tasks
- [x] Install and configure `fastapi-csrf-protect`
- [x] Add CSRF token to all forms in templates
- [x] Validate CSRF token on all POST routes
- [x] Ensure CSRF token is included in test client requests

### Tests (write FIRST)
```
test_post_without_csrf_token_rejected
test_post_with_valid_csrf_token_accepted
test_post_with_invalid_csrf_token_rejected
test_csrf_token_present_in_all_forms
```

### Acceptance Criteria
- [x] All POST requests require a valid CSRF token
- [x] Forms include hidden CSRF token field
- [x] All existing tests updated to include CSRF tokens
- [x] All CSRF tests pass

---

## Phase 15: PWA Support

### Tasks
- [x] Create `app/static/manifest.json`
- [x] Create `app/static/sw.js` (service worker)
- [x] Create/add PWA icons (192x192, 512x512)
- [x] Add manifest link and service worker registration to `base.html`
- [x] Configure cache strategy (cache-first for static assets)

### Tests (write FIRST)
```
test_manifest_json_accessible
test_manifest_json_valid_structure
test_service_worker_accessible
test_base_template_includes_manifest_link
test_base_template_registers_service_worker
test_pwa_icons_accessible
```

### Acceptance Criteria
- [x] App is installable on mobile devices
- [x] manifest.json is valid and served correctly
- [x] Service worker caches static assets
- [x] PWA icons are present and correctly sized
- [x] All PWA tests pass

---

## Phase 16: Validation & Polish

### Tasks
- [x] Review all form validation — client-side (HTML5 + Alpine.js) AND server-side
- [x] Add user-friendly error messages for all validation failures
- [x] Add loading states / disabled buttons on form submission
- [x] Ensure all flash messages are clear and actionable
- [x] Test all flows end-to-end manually
- [x] Review all queries for N+1 issues (use `joinedload` where needed)
- [x] Add rate limiting on login/register/password-reset routes
- [x] Add logging (Python `logging` module) for errors and important events

### Tests (write FIRST)
```
test_all_forms_have_required_field_validation
test_server_validation_matches_schema_rules
test_flash_messages_on_success_actions
test_flash_messages_on_error_actions
test_no_n_plus_1_queries_on_dashboard
test_no_n_plus_1_queries_on_vehicle_list
test_no_n_plus_1_queries_on_fuel_entry_list
```

### Acceptance Criteria
- [x] No unhandled exceptions on any user flow
- [x] All validation errors show user-friendly messages
- [x] No N+1 query issues
- [x] Login/register routes are rate-limited
- [x] All polish tests pass

---

## Phase 17: Maintenance Logs & Service Reminders

**Status:** ✅ Complete (post–Phase 16 delivery)

### Tasks
- [x] `MaintenanceLog` model (service date, usage, cost, next service date/usage, reminders)
- [x] `app/routes/maintenance.py` — CRUD (contributor create/edit, admin delete)
- [x] `app/services/reminders.py` — due reminders for dashboard + email
- [x] `POST /cron/service-reminders` — Bearer `CRON_SECRET`, Brevo email to farm admins
- [x] Audit: `maintenance.create`, `maintenance.update`, `maintenance.delete`
- [x] Tests in `tests/test_l_features.py`

### Acceptance criteria
- [x] Contributors can log maintenance; readers cannot mutate
- [x] Cron sends due service reminders when mail is configured
- [x] Maintenance appears in nav (`/maintenance`)

---

## Phase 18: Analytics, Export, Cost & Partial Fill

**Status:** ✅ Complete

### Tasks
- [x] `FuelEntry.full_tank` and `FuelEntry.total_cost_eur`
- [x] Consumption excludes partial-fill segments (`app/services/consumption.py`)
- [x] Summary/dashboard cost totals
- [x] `GET /analytics` — group analytics page
- [x] `GET /export/fuel-entries.csv`, `GET /export/vehicles.csv`
- [x] Tests in `tests/test_sm_features.py`

### Acceptance criteria
- [x] Partial fills do not skew consumption averages
- [x] CSV export includes cost and full-tank columns
- [x] Analytics page requires auth + active group

---

## Phase 19: Audit Log UI

**Status:** ✅ Complete (extends Phase 13 backend)

### Tasks
- [x] `GET /settings/audit` — farm admin only
- [x] `app/services/audit_ui.py` — list recent events for group
- [x] Link from group settings page
- [x] Tests in `tests/test_sm_features.py`, `tests/test_audit_log.py`

### Acceptance criteria
- [x] Farm admins can view audit history for their group
- [x] Non-admins receive 403

---

## Phase 20: Session Revocation & Production Hardening

**Status:** ✅ Complete

### Tasks
- [x] `UserSession` table — server-side sessions with revoke support (see D-046)
- [x] Signed cookie carries `session_id` + `user_id` + `active_group_id`
- [x] Profile: list/revoke sessions; password change revokes other sessions
- [x] `GET /health`, `GET /health/ready` — liveness/readiness probes
- [x] Security headers middleware, CSP (self-hosted assets only)
- [x] Production config validation (`SECRET_KEY`, `CRON_SECRET`, `REDIS_URL` / `SINGLE_WORKER_MODE`)
- [x] Redis-backed rate limits when `REDIS_URL` set; in-memory fallback for beta
- [x] Error pages for 404/500
- [x] Tests: `tests/test_l_features.py`, `tests/test_production_hardening.py`, `tests/test_error_pages.py`

### Acceptance criteria
- [x] Revoked sessions cannot access protected routes
- [x] Production env rejects default `SECRET_KEY` and missing `CRON_SECRET`
- [x] Readiness probe fails when DB unreachable

---

## Phase 21: Marketing Site & Private Beta Gating

**Status:** ✅ Complete

### Tasks
- [x] `app/routes/marketing.py` — landing (`/`), `/impressum`, `/datenschutz`, `/agb`, `/robots.txt`
- [x] `REGISTRATION_INVITE_CODE` — optional registration gate for private beta
- [x] `noindex` + robots blocking when invite gate enabled
- [x] Self-hosted Tailwind/Alpine in `app/static/vendor/` (no CDN in production CSP)
- [x] Tests: `tests/test_marketing.py`, `tests/test_private_beta.py`, `tests/test_vendor_assets.py`

### Acceptance criteria
- [x] Anonymous users see landing page; authenticated users redirect to app
- [x] Invalid/missing invite code blocks registration when configured
- [x] Login page loads without external CDN scripts

---

## Phase 22: Platform Admin (Operator Dashboard)

**Status:** ✅ Complete (Phase 1 read-only dashboard + Phase 2 support view)

Full specification: [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md)

### Summary
- [x] `PLATFORM_ADMIN_EMAILS` env allowlist
- [x] Read-only `/platform/farms`, `/platform/users`
- [x] Phase 2: support “view farm” session (read-only)
- [x] `tests/test_platform_admin.py`

### Acceptance criteria
- [x] Operator can list all farms and search users cross-tenant
- [x] Non-operators cannot access `/platform/*`
- [x] Platform actions audit-logged (farm detail, user search, user detail, enter, exit)
- [x] Support view is read-only (mutations and exports blocked)

---

## Phase 23: Stripe Billing

**Status:** ⬜ Planned — **not implemented**

Full specification: [STRIPE_BILLING.md](./STRIPE_BILLING.md)

### Summary
- [ ] `group_subscriptions` table + webhooks
- [ ] Checkout + customer portal
- [ ] Entitlements / tier limits per group
- [ ] Sync `groups.subscription_tier`

---

## Phase 24: AdBlue on Tractor Entries

**Status:** ✅ Complete

Full specification: [TANK_INVENTORY_AND_ADBLUE.md](./TANK_INVENTORY_AND_ADBLUE.md) § Phase 24

### Summary
- [x] `fuel_entries.adblue_amount_l` optional column
- [x] Tractor-only validation; separate summary totals
- [x] `tests/test_adblue.py`

### Tests (write before implementation)
```
test_fuel_entry_create_with_adblue_on_tractor
test_fuel_entry_create_without_adblue_on_tractor_ok
test_fuel_entry_create_adblue_on_car_rejected
test_fuel_entry_create_adblue_zero_rejected
test_fuel_entry_update_clears_adblue
test_fuel_entry_form_shows_adblue_for_tractor_vehicle
test_fuel_entry_form_hides_adblue_for_car
test_summary_includes_adblue_total_separate_from_fuel_liters
test_consumption_ignores_adblue_amount
test_export_csv_includes_adblue_column
```

### Acceptance criteria
- [x] Tractor entries may record optional AdBlue liters
- [x] Non-tractors cannot save AdBlue; diesel consumption unchanged
- [x] AdBlue totals separate from Kraftstoff liters in summary/export

---

## Phase 25: Storage Tanks & Ledger

**Status:** ✅ Complete

Full specification: [TANK_INVENTORY_AND_ADBLUE.md](./TANK_INVENTORY_AND_ADBLUE.md) § Phase 25

### Summary
- [x] `StorageTank` + `TankLedgerEntry` models and migration
- [x] Multiple tanks per fuel type per group
- [x] Deliveries, adjustments, computed `current_stock_l`
- [x] `/tanks` CRUD UI
- [x] `tests/test_storage_tanks.py`, `tests/test_tank_ledger.py`

### Tests (write before implementation)
```
test_storage_tank_create_diesel
test_storage_tank_create_second_petrol_tank_same_group_allowed
test_storage_tank_list_scoped_to_active_group
test_storage_tank_detail_404_other_group
test_storage_tank_soft_delete_hidden_from_list
test_storage_tank_update_name_and_capacity
test_storage_tank_delete_requires_admin
test_storage_tank_reader_can_view_not_create
test_current_stock_opening_balance_only
test_current_stock_includes_deliveries
test_current_stock_excludes_soft_deleted_ledger_rows
test_delivery_creates_positive_ledger_entry
test_adjustment_requires_notes
test_adjustment_admin_only
test_adjustment_allows_negative_amount
test_negative_stock_computed_allowed
test_ledger_entry_group_id_must_match_tank_group
```

### Acceptance criteria
- [x] Farm can create multiple Benzin/Diesel tanks
- [x] Stock = opening balance + ledger sum; deliveries increase stock

---

## Phase 26: Fill Source & Tank Selection on Fuel Entries

**Status:** ✅ Complete

Full specification: [TANK_INVENTORY_AND_ADBLUE.md](./TANK_INVENTORY_AND_ADBLUE.md) § Phase 26

### Summary
- [x] `fill_source` + `fuel_tank_id` on `FuelEntry` (default external)
- [x] Auto `vehicle_withdrawal` ledger sync
- [x] Tank dropdown filtered by vehicle fuel type; explicit choice when multiple tanks
- [x] `tests/test_fuel_fill_source.py`

### Tests (write before implementation)
```
test_fuel_entry_default_fill_source_external
test_fuel_entry_farm_fill_requires_tank_id
test_fuel_entry_farm_fill_wrong_fuel_type_rejected
test_fuel_entry_farm_fill_creates_vehicle_withdrawal_ledger
test_fuel_entry_external_fill_no_ledger_row
test_fuel_entry_farm_fill_deducts_correct_tank_stock
test_fuel_entry_multiple_petrol_tanks_must_choose_tank
test_fuel_entry_single_petrol_tank_preselected
test_fuel_entry_update_liters_updates_ledger_amount
test_fuel_entry_change_farm_to_external_removes_ledger
test_fuel_entry_change_external_to_farm_creates_ledger
test_fuel_entry_delete_soft_deletes_linked_ledger
test_fuel_entry_farm_tank_other_group_404
test_fuel_entry_form_tank_dropdown_lists_only_matching_fuel_type
test_existing_entries_without_fill_source_treated_as_external
```

### Acceptance criteria
- [x] User chooses which tank when tanking at farm; external fills do not affect inventory
- [x] Legacy entries behave as external

---

## Phase 27: External Withdrawals at Farm Tanks

**Status:** ✅ Complete

Full specification: [TANK_INVENTORY_AND_ADBLUE.md](./TANK_INVENTORY_AND_ADBLUE.md) § Phase 27

### Summary
- [x] Externe Abgabe flow (recipient name, no vehicle)
- [x] Excluded from dashboard/summary/analytics
- [x] `tests/test_tank_external.py`

### Tests (write before implementation)
```
test_external_withdrawal_creates_ledger_not_fuel_entry
test_external_withdrawal_requires_recipient_name
test_external_withdrawal_reduces_tank_stock
test_external_withdrawal_excluded_from_dashboard_fuel_liters
test_external_withdrawal_excluded_from_summary_vehicle_totals
test_external_withdrawal_excluded_from_analytics
test_external_withdrawal_other_group_tank_404
test_external_withdrawal_soft_delete_restores_stock
```

### Acceptance criteria
- [x] Third-party fills tracked per tank; fleet statistics unchanged

---

## Phase 28: Tank Dashboard & Exports

**Status:** ✅ Complete

Full specification: [TANK_INVENTORY_AND_ADBLUE.md](./TANK_INVENTORY_AND_ADBLUE.md) § Phase 28

### Summary
- [x] Dashboard tank stock cards; negative-stock warning
- [x] Extended fuel CSV + optional tank-ledger CSV
- [x] Nav link Tanklager

### Tests (write before implementation)
```
test_dashboard_shows_tank_stock_when_tanks_exist
test_dashboard_negative_stock_shows_warning
test_dashboard_no_tanks_hides_stock_section
test_export_fuel_entries_includes_fill_source_and_tank_name
test_export_tank_ledger_csv_scoped_to_group
```

### Acceptance criteria
- [x] Users see Hof-Tank levels on dashboard; exports include new fields

---

## Cross-Cutting Test Requirements

### Security Tests (run across all phases)
```
test_all_post_routes_require_csrf
test_all_protected_routes_require_auth
test_all_group_scoped_routes_check_membership
test_no_route_leaks_data_from_other_groups
test_passwords_never_appear_in_responses
test_session_cookie_is_httponly
test_session_cookie_is_secure_in_production
test_session_cookie_has_samesite
```

### Soft Delete Tests (run across all phases)
```
test_soft_deleted_users_cannot_login
test_soft_deleted_groups_not_listed
test_soft_deleted_vehicles_not_listed
test_soft_deleted_fuel_entries_not_listed
test_soft_deleted_records_excluded_from_statistics
```

---

## Test Infrastructure Summary

| Category          | Approx. Test Count |
|-------------------|--------------------|
| Models            | ~25                |
| Schemas           | ~20                |
| Auth              | ~25                |
| Password Reset    | ~12                |
| Groups            | ~20                |
| Templates/UI      | ~8                 |
| Dashboard         | ~10                |
| Vehicles          | ~20                |
| Fuel Entries      | ~25                |
| Profile           | ~10                |
| Summary/Stats     | ~15                |
| Group Settings    | ~18                |
| Audit Logging     | ~13                |
| CSRF              | ~4                 |
| PWA               | ~6                 |
| Validation/Polish | ~7                 |
| Security (cross)  | ~8                 |
| Soft Delete (cross)| ~5                |
| Maintenance & cron (Phase 17) | ~15      |
| Analytics/export/cost (Phase 18–19) | ~20 |
| Production & beta (Phase 20–21) | ~25   |
| Platform admin (Phase 22) | ~28 |
| AdBlue (Phase 24) | ~10 |
| Storage tanks & ledger (Phase 25) | ~17 |
| Fill source (Phase 26) | ~15 |
| External withdrawal (Phase 27) | ~8 |
| Tank dashboard & export (Phase 28) | ~5 |
| **Total (current)** | **~479**         |
| **Total (with Phases 24–28)** | **~479**         |

---

## Dependency Installation Order

See `requirements-prod.txt` (deploy) and `requirements-dev.txt` (local/CI). Summary:

```
# Core (prod)
fastapi, uvicorn[standard], sqlalchemy, alembic, psycopg2-binary
pydantic[email], pydantic-settings, python-dotenv, jinja2
python-multipart, itsdangerous, bcrypt, aiofiles

# Email
fastapi-mail

# Security & ops
fastapi-csrf-protect
redis                    # production rate limits (optional in beta with SINGLE_WORKER_MODE)
sentry-sdk[fastapi]      # optional

# Dev / CI only (requirements-dev.txt)
pytest, pytest-asyncio, pytest-cov, httpx, ruff
```

Planned Phase 23: add `stripe` — see [STRIPE_BILLING.md](./STRIPE_BILLING.md).
