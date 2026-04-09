# TankApp – Test-Driven Development Plan

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
  - `create_session_cookie(user_id, active_group_id)` → signed cookie value
  - `decode_session_cookie(cookie_value)` → dict or None
- [x] Create `app/dependencies.py`:
  - `get_current_user(request)` → User or redirect to login
  - `get_active_group(request)` → Group or redirect to group selection
  - `require_role(min_role)` → dependency factory
- [x] Create `app/routes/auth.py`:
  - `GET /login` — render login form
  - `POST /login` — authenticate, set cookie, redirect
  - `GET /register` — render registration form
  - `POST /register` — create user, set cookie, redirect
  - `POST /logout` — clear cookie, redirect to login

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
- [ ] Create `app/routes/groups.py`:
  - `GET /groups` — list user's groups, show create/join forms
  - `POST /groups/create` — create group, set user as admin
  - `POST /groups/join` — join via invite code, set as contributor
  - `POST /groups/switch/{id}` — switch active group in session
  - `POST /groups/leave/{id}` — leave group (admin can't leave if sole admin)
  - `POST /groups/delete/{id}` — soft-delete group (admin only)
- [ ] Generate invite codes (format: `FARM-XXXXX`, alphanumeric)
- [ ] After registration: redirect to group selection if no groups exist

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
- [ ] Users can create groups and become admin
- [ ] Users can join groups via invite code
- [ ] Users can switch between groups
- [ ] Users can leave groups (with sole-admin protection)
- [ ] Admins can soft-delete groups
- [ ] Group context is maintained in session
- [ ] All group tests pass

---

## Phase 6: Base Template & Layout

### Tasks
- [ ] Create `app/templates/base.html`:
  - Tailwind CSS (CDN)
  - Alpine.js (CDN)
  - Navigation bar (responsive, mobile hamburger menu)
  - Flash message display area
  - Active group indicator
  - User name display
  - Logout button
  - Footer
- [ ] Create `app/templates/login.html`
- [ ] Create `app/templates/register.html`
- [ ] Create `app/templates/groups.html`
- [ ] Set up static file serving in FastAPI
- [ ] Implement flash message system (via cookie or query param)

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
- [ ] All pages inherit from base template
- [ ] Navigation is responsive (mobile-friendly)
- [ ] Flash messages appear after actions (success/error)
- [ ] Active group name visible in nav
- [ ] All template tests pass

---

## Phase 7: Dashboard

### Tasks
- [ ] Create `app/routes/dashboard.py`:
  - `GET /dashboard` — render dashboard with statistics
- [ ] Create `app/templates/dashboard.html`:
  - Total vehicles count
  - Total fuel entries count
  - Total fuel liters
  - Recent fuel entries (last 5–10)
- [ ] Dashboard scoped to active group

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
- [ ] Dashboard displays correct counts for active group
- [ ] Soft-deleted records are excluded
- [ ] Empty state is handled gracefully
- [ ] All dashboard tests pass

---

## Phase 8: Vehicles CRUD

### Tasks
- [ ] Create `app/routes/vehicles.py`:
  - `GET /vehicles` — list vehicles (active group, exclude soft-deleted)
  - `GET /vehicles/new` — render create form (admin, contributor)
  - `POST /vehicles/new` — create vehicle (auto-set usage_unit)
  - `GET /vehicles/{id}/edit` — render edit form (admin, contributor)
  - `POST /vehicles/{id}/edit` — update vehicle
  - `POST /vehicles/{id}/delete` — soft-delete vehicle (admin only)
- [ ] Create `app/templates/vehicles.html`
- [ ] Create `app/templates/vehicle_form.html`

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
- [ ] CRUD operations work for vehicles within active group
- [ ] `usage_unit` is auto-set from `vtype`, not editable
- [ ] Soft delete preserves data, hides from list
- [ ] Role-based access is enforced
- [ ] Cross-group access is denied
- [ ] All vehicle tests pass

---

## Phase 9: Fuel Entries CRUD

### Tasks
- [ ] Create `app/routes/fuel_entries.py`:
  - `GET /fuel` — list fuel entries (active group, exclude soft-deleted)
  - `GET /fuel/new` — render create form with vehicle dropdown (admin, contributor)
  - `POST /fuel/new` — create fuel entry
  - `GET /fuel/{id}/edit` — render edit form (admin, contributor)
  - `POST /fuel/{id}/edit` — update fuel entry
  - `POST /fuel/{id}/delete` — soft-delete fuel entry (admin only)
- [ ] Create `app/templates/fuel_entries.html`
- [ ] Create `app/templates/fuel_entry_form.html`
- [ ] Validate `group_id` matches `vehicle.group_id` on creation
- [ ] Vehicle dropdown only shows non-deleted vehicles from active group

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
- [ ] CRUD operations work for fuel entries within active group
- [ ] `group_id` is auto-set to match the vehicle's group
- [ ] `user_id` is auto-set from the session
- [ ] Validation prevents invalid data
- [ ] Cross-group access is denied
- [ ] Role-based access is enforced
- [ ] All fuel entry tests pass

---

## Phase 10: User Profile Management

### Tasks
- [ ] Create `app/routes/profile.py`:
  - `GET /profile` — render profile page
  - `POST /profile` — update name and/or email
  - `POST /profile/change-password` — change password
- [ ] Create `app/templates/profile.html`

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
- [ ] Users can view and update their profile
- [ ] Users can change their password
- [ ] Email uniqueness is enforced
- [ ] All profile tests pass

---

## Phase 11: Summary & Statistics

### Tasks
- [ ] Create `app/routes/summary.py`:
  - `GET /summary` — render summary page with statistics
- [ ] Create `app/templates/summary.html`
- [ ] Implement consumption calculation logic (see D-004)
- [ ] Display:
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
- [ ] Summary shows fuel totals per vehicle
- [ ] Summary shows monthly fuel totals
- [ ] Consumption averages are calculated correctly per D-004
- [ ] Empty states handled gracefully
- [ ] All summary tests pass

---

## Phase 12: Group Settings

### Tasks
- [ ] Create `app/routes/group_settings.py`:
  - `GET /settings/group` — render group settings page
  - `POST /settings/group/regenerate-code` — regenerate invite code (admin)
  - `POST /settings/group/members/{user_id}/role` — change member role (admin)
  - `POST /settings/group/members/{user_id}/remove` — remove member (admin)
- [ ] Create `app/templates/group_settings.html`:
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
- [ ] Group settings page shows invite code and members
- [ ] Admins can regenerate invite codes
- [ ] Admins can change member roles
- [ ] Admins can remove members
- [ ] Self-demotion/removal is prevented for sole admins
- [ ] All group settings tests pass

---

## Phase 13: Audit Logging

### Tasks
- [ ] Create `app/audit.py`:
  - `log_event(db, group_id, user_id, action, entity_type, entity_id)` helper function
- [ ] Integrate audit logging into relevant route handlers (see D-006 for event list)
- [ ] Optionally: display recent audit events in group settings

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
- [ ] Important events are logged per D-006
- [ ] Routine operations are NOT logged
- [ ] Audit log entries have correct metadata
- [ ] All audit tests pass

---

## Phase 14: CSRF Protection

### Tasks
- [ ] Install and configure `fastapi-csrf-protect`
- [ ] Add CSRF token to all forms in templates
- [ ] Validate CSRF token on all POST routes
- [ ] Ensure CSRF token is included in test client requests

### Tests (write FIRST)
```
test_post_without_csrf_token_rejected
test_post_with_valid_csrf_token_accepted
test_post_with_invalid_csrf_token_rejected
test_csrf_token_present_in_all_forms
```

### Acceptance Criteria
- [ ] All POST requests require a valid CSRF token
- [ ] Forms include hidden CSRF token field
- [ ] All existing tests updated to include CSRF tokens
- [ ] All CSRF tests pass

---

## Phase 15: PWA Support

### Tasks
- [ ] Create `app/static/manifest.json`
- [ ] Create `app/static/sw.js` (service worker)
- [ ] Create/add PWA icons (192x192, 512x512)
- [ ] Add manifest link and service worker registration to `base.html`
- [ ] Configure cache strategy (cache-first for static assets)

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
- [ ] App is installable on mobile devices
- [ ] manifest.json is valid and served correctly
- [ ] Service worker caches static assets
- [ ] PWA icons are present and correctly sized
- [ ] All PWA tests pass

---

## Phase 16: Validation & Polish

### Tasks
- [ ] Review all form validation — client-side (HTML5 + Alpine.js) AND server-side
- [ ] Add user-friendly error messages for all validation failures
- [ ] Add loading states / disabled buttons on form submission
- [ ] Ensure all flash messages are clear and actionable
- [ ] Test all flows end-to-end manually
- [ ] Review all queries for N+1 issues (use `joinedload` where needed)
- [ ] Add rate limiting on login/register/password-reset routes
- [ ] Add logging (Python `logging` module) for errors and important events

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
- [ ] No unhandled exceptions on any user flow
- [ ] All validation errors show user-friendly messages
- [ ] No N+1 query issues
- [ ] Login/register routes are rate-limited
- [ ] All polish tests pass

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
| **Total**         | **~251**           |

---

## Dependency Installation Order

```
# Core
fastapi
uvicorn[standard]
sqlalchemy
alembic
pydantic[email]
pydantic-settings
python-dotenv
jinja2
python-multipart
itsdangerous
bcrypt
aiofiles

# Email (password reset)
fastapi-mail

# Security
fastapi-csrf-protect

# Testing
pytest
pytest-asyncio
httpx
```
