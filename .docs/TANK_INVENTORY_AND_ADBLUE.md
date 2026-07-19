# Tankly – Farm Tank Inventory, Fill Sources & AdBlue

Implementation guide for **physical farm tank tracking** (Lagerbestände), **vehicle fill sources** (eigene vs. externe Tankstelle), **external withdrawals** at farm tanks, and **optional AdBlue** on tractor fuel entries.

**Status:** ✅ Complete (Development Plan Phases 24–28).

**Prerequisites:** Phases 0–22 complete. May be implemented **before or after** Phase 23 (Stripe billing); no billing dependency.

**Related docs:** [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) · [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) · [DECISION_LOG.md](./DECISION_LOG.md)

---

## Table of contents

1. [Problem & goals](#1-problem--goals)
2. [Current state vs target state](#2-current-state-vs-target-state)
3. [Domain model](#3-domain-model)
4. [Business rules](#4-business-rules)
5. [Statistics & reporting](#5-statistics--reporting)
6. [UI & routes](#6-ui--routes)
7. [Implementation phases (TDD)](#7-implementation-phases-tdd)
8. [Database migration](#8-database-migration)
9. [Services & file layout](#9-services--file-layout)
10. [Authorization](#10-authorization)
11. [CSV export & profile data export](#11-csv-export--profile-data-export)
12. [Open decisions (for DECISION_LOG)](#12-open-decisions-for-decision_log)
13. [Implementation pitfalls](#13-implementation-pitfalls)

---

## 1. Problem & goals

Today Tankly records **vehicle fuel events** (`FuelEntry`) only. Farms also need:

| # | Requirement | Outcome |
|---|-------------|---------|
| 1 | **AdBlue** on tractor tankings | Optional liters alongside diesel on the same entry; separate from diesel consumption stats |
| 2 | **Lagerbestände** | Per-farm storage tanks (diesel, benzin) with stock levels, deliveries, and movement history |
| 3 | **Multiple tanks per fuel type** | e.g. two Benzin tanks — user **must choose which tank** on every farm-sourced fill or external withdrawal |
| 4 | **External people** at farm tanks | Track liters leaving inventory (e.g. neighbor “Kreuzmayr”); **exclude from all vehicle/fleet statistics** |
| 5 | **Own vehicles, mixed sources** | Record tankings at public stations (stats yes, inventory no) vs. own farm tanks (stats yes, inventory deducted) |

**Non-goals (v1):**

- AdBlue tank inventory (log AdBlue liters only; no AdBlue `StorageTank`)
- Heating oil or fuels beyond existing `FuelType` (`diesel`, `petrol`)
- Automatic fuel-type detection from receipts
- Audit log entries for every tank movement (follow D-042: structural changes only; tank CRUD may be logged like vehicles)

---

## 2. Current state vs target state

### Current state

| Area | Status |
|------|--------|
| `FuelEntry` → vehicle liters, cost, full/partial | ✅ |
| `Vehicle.fuel_type` diesel / petrol | ✅ |
| Fleet stats via `active_fuel_entries_for_group()` | ✅ |
| Physical storage tanks | ❌ |
| Fill source (farm vs external) | ❌ |
| External person withdrawals | ❌ (import script skips unmapped names) |
| AdBlue | ❌ |

### Target state

```
Group (farm)
  ├── StorageTank[]          — multiple per fuel_type allowed
  │     └── TankLedgerEntry[] — deliveries, withdrawals, adjustments
  ├── Vehicle[]
  │     └── FuelEntry[]       — fill_source, fuel_tank_id?, adblue_amount_l?
  └── (stats)                 — vehicle entries only; ledger external withdrawals excluded
```

---

## 3. Domain model

### 3.1 New enums (`app/enums.py`)

```python
class FillSource(str, Enum):
    external = "external"   # public / third-party station — default
    farm = "farm"           # drawn from farm StorageTank

class TankMovementType(str, Enum):
    delivery = "delivery"                   # + liters into tank
    vehicle_withdrawal = "vehicle_withdrawal"   # − liters; linked FuelEntry
    external_withdrawal = "external_withdrawal" # − liters; recipient_name
    adjustment = "adjustment"               # +/− liters; manual correction
```

### 3.2 `StorageTank` (table: `storage_tanks`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | |
| `group_id` | FK → groups | |
| `name` | str | e.g. “Benzin Werkstatt” — **not unique** within group |
| `fuel_type` | enum | `diesel` \| `petrol` |
| `capacity_l` | float \| null | optional; for % full UI |
| `opening_balance_l` | float | default `0`; stock baseline at tank creation |
| `notes` | str \| null | max 500 |
| `created_at` | datetime | |
| `updated_at` | datetime \| null | |
| `deleted_at` | datetime \| null | soft delete |

**Constraints:**

- `opening_balance_l >= 0`
- `capacity_l` is null or `capacity_l > 0`
- **No** unique constraint on `(group_id, fuel_type)` — multiple Benzin tanks allowed

**Relationships:** `Group.storage_tanks`, `StorageTank.ledger_entries`

### 3.3 `TankLedgerEntry` (table: `tank_ledger_entries`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | |
| `tank_id` | FK → storage_tanks | |
| `group_id` | FK → groups | denormalized (D-003 pattern) |
| `user_id` | FK → users | who recorded it |
| `movement_type` | enum | see `TankMovementType` |
| `amount_l` | float | **signed**: positive = in, negative = out |
| `entry_date` | date | |
| `fuel_entry_id` | FK → fuel_entries \| null | set for `vehicle_withdrawal` |
| `recipient_name` | str \| null | required for `external_withdrawal` |
| `total_cost_eur` | float \| null | optional (delivery cost or external sale) |
| `notes` | str \| null | max 500 |
| `created_at` | datetime | |
| `updated_at` | datetime \| null | |
| `deleted_at` | datetime \| null | soft delete |

**Constraints:**

- `amount_l != 0`
- `fuel_entry_id` set iff `movement_type == vehicle_withdrawal`
- `recipient_name` non-empty iff `movement_type == external_withdrawal`
- On create: validate `tank.group_id == entry.group_id`
- On create: validate `fuel_entry.group_id == entry.group_id` when linked

**Stock calculation (computed, never stored):**

```text
current_stock_l(tank) = opening_balance_l
  + SUM(amount_l) for non-deleted TankLedgerEntry where tank_id = tank.id
```

Negative stock is **allowed** with a UI warning (D-054).

### 3.4 `FuelEntry` extensions

| Column | Type | Notes |
|--------|------|-------|
| `fill_source` | enum | default `external` |
| `fuel_tank_id` | FK → storage_tanks \| null | required when `fill_source == farm` |
| `adblue_amount_l` | float \| null | optional; only for tractors |

**Constraints:**

- `fill_source == farm` ⇒ `fuel_tank_id` not null
- `fill_source == external` ⇒ `fuel_tank_id` null
- Linked tank `fuel_type` must match vehicle `fuel_type`
- Linked tank must be active (non-deleted) in same group
- `adblue_amount_l` is null or `adblue_amount_l > 0`
- If vehicle `vtype != tractor` ⇒ `adblue_amount_l` must be null (schema + service)

**Side effect on save (farm fill):**

When a `FuelEntry` is created or updated with `fill_source=farm`, atomically create/update a linked `TankLedgerEntry`:

- `movement_type = vehicle_withdrawal`
- `amount_l = -fuel_amount_l` (diesel/benzin only — **not** AdBlue)
- `fuel_entry_id = entry.id`

When `fill_source` changes from `farm` → `external`, soft-delete the linked ledger row. When liters change on farm fill, update the linked row. On fuel entry soft-delete, soft-delete linked ledger row.

---

## 4. Business rules

### 4.1 Multiple tanks, explicit selection

- A group may have **any number** of `StorageTank` rows per `fuel_type`.
- On **Tankvorgang** with `fill_source=farm`, the user **must** select `fuel_tank_id` from tanks matching the vehicle’s `fuel_type`.
- Dropdown shows tank name and current stock, e.g. `Benzin Hof (380 L)`.
- If **exactly one** matching tank exists: **pre-select** in the form, but field remains visible and submittable.
- If **zero** matching tanks: farm source invalid — show validation error (“Kein passender Tank angelegt”).
- If **two or more** matching tanks and none selected: validation error (“Tank auswählen”).

Same tank picker on **Externe Abgabe** (filtered by chosen fuel type or selected tank only).

### 4.2 Fill source defaults

| Scenario | Default `fill_source` |
|----------|----------------------|
| New entry, existing data / no tanks | `external` |
| New entry, group has ≥1 tank matching vehicle fuel type | `external` (safe default; user opts in to farm) |
| Imported / API entries without field | `external` |

Rationale: avoid accidental inventory deductions before tanks are configured.

### 4.3 External withdrawal (no vehicle)

- Dedicated flow: pick tank, liters, date, `recipient_name`, optional cost/notes.
- Creates `TankLedgerEntry` with `movement_type=external_withdrawal`, `amount_l = -liters`.
- **Never** creates a `FuelEntry`.
- Excluded from all fleet statistics by construction.

### 4.4 Deliveries & adjustments

- **Delivery:** admin/contributor posts positive `amount_l`, optional cost, date, notes.
- **Adjustment:** admin only; signed `amount_l`; notes **required** (explain correction).

### 4.5 AdBlue (tractors only)

- Optional field on the same form as diesel liters.
- Does **not** affect `fuel_amount_l`, consumption, or tank inventory in v1.
- Included in AdBlue-specific aggregates (summary/dashboard) when present.

### 4.6 Soft delete

- Soft-deleted tanks: hidden from pickers; existing ledger rows remain for history; stock calc excludes deleted ledger rows.
- Soft-deleted ledger entries: excluded from stock sum.
- Soft-deleted fuel entry: linked `vehicle_withdrawal` ledger row also soft-deleted.

---

## 5. Statistics & reporting

### 5.1 Unchanged scope for fleet stats

`active_fuel_entries_for_group()` continues to drive dashboard, summary, analytics, and consumption. External withdrawals are **not** fuel entries and never enter this query.

### 5.2 Consumption (D-004, D-048)

- Consumption uses `fuel_amount_l` only (diesel/benzin).
- AdBlue never participates in `average_consumption_for_vehicle()`.

### 5.3 New aggregates

| Metric | Source |
|--------|--------|
| Per-tank `current_stock_l` | computed from opening + ledger |
| Per-tank low-stock flag | `current_stock_l < 0` or optional % of `capacity_l` |
| Group AdBlue total (period) | `SUM(adblue_amount_l)` on tractor fuel entries |
| Per-vehicle AdBlue (optional) | same filter, grouped by vehicle |

### 5.4 CSV export

Extend `fuel_entries_csv` with columns: `fill_source`, `fuel_tank_name`, `adblue_amount_l`.

New export: `tank-ledger.csv` (or per-tank) — optional Phase 28.

---

## 6. UI & routes

### 6.1 Navigation

Add **Tanklager** link in `base.html` when active group is set (all roles can view; contributors+ can post movements; admins delete).

### 6.2 Tank management

| Method | Route | Role | Action |
|--------|-------|------|--------|
| GET | `/tanks` | reader+ | List tanks with stock |
| GET | `/tanks/new` | contributor+ | Create form |
| POST | `/tanks/new` | contributor+ | Create tank |
| GET | `/tanks/{id}` | reader+ | Detail: stock, recent ledger |
| GET | `/tanks/{id}/edit` | contributor+ | Edit form |
| POST | `/tanks/{id}/edit` | contributor+ | Update |
| POST | `/tanks/{id}/delete` | admin | Soft delete |

### 6.3 Ledger actions

| Method | Route | Role | Action |
|--------|-------|------|--------|
| GET | `/tanks/{id}/delivery/new` | contributor+ | Delivery form |
| POST | `/tanks/{id}/delivery/new` | contributor+ | Post delivery |
| GET | `/tanks/{id}/external/new` | contributor+ | External withdrawal form |
| POST | `/tanks/{id}/external/new` | contributor+ | Post external withdrawal |
| GET | `/tanks/ledger/{id}/edit` | contributor+ | Edit adjustment/delivery/external |
| POST | `/tanks/ledger/{id}/edit` | contributor+ | Update |
| POST | `/tanks/ledger/{id}/delete` | admin | Soft delete ledger row |

`vehicle_withdrawal` rows are **not** edited directly — edit the linked `FuelEntry` instead (or block with message).

### 6.4 Fuel entry form changes

Sections added to `fuel_entry_form.html`:

1. **Tankquelle** — radio: `Externe Tankstelle` (default) | `Eigene Tankstelle`
2. **Tank** — `<select name="fuel_tank_id">` visible when farm; options = active tanks matching vehicle fuel type (HTMX or Alpine: update on vehicle change on create form)
3. **AdBlue** — optional liters; visible only when selected vehicle `vtype == tractor`

### 6.5 Templates (new)

- `tanks.html` — list
- `tank_form.html` — create/edit storage tank
- `tank_detail.html` — stock + ledger table
- `tank_delivery_form.html`
- `tank_external_form.html`
- `tank_ledger_edit_form.html` — delivery/external/adjustment only

### 6.6 German UI labels

| Internal | UI (de) |
|----------|---------|
| `StorageTank` | Tanklager / Hof-Tank |
| `fill_source.external` | Externe Tankstelle |
| `fill_source.farm` | Eigene Tankstelle |
| `external_withdrawal` | Externe Abgabe |
| `delivery` | Lieferung / Auffüllung |
| `adjustment` | Bestandskorrektur |
| `adblue_amount_l` | AdBlue (Liter) |

---

## 7. Implementation phases (TDD)

Follow **Red → Green → Refactor** per [copilot-instructions](../.github/copilot-instructions.md). Write **all** tests listed for a phase before implementation.

### Phase 24 — AdBlue on tractor entries

**Goal:** Optional AdBlue without inventory or fill-source changes.

**Files:** `app/models.py`, `app/schemas.py`, `app/services/fuel_entries.py`, `app/routes/fuel_entries.py`, `app/templates/fuel_entry_form.html`, `app/services/summary.py` (AdBlue totals), Alembic migration, `tests/test_adblue.py`, extend `tests/test_schemas.py`.

**Tasks:**

- [x] Migration: `fuel_entries.adblue_amount_l` nullable float
- [x] `FuelEntryCreate` / `FuelEntryUpdate`: optional `adblue_amount_l`; reject on non-tractor vehicles
- [x] Form: show AdBlue field when tractor selected
- [x] Summary: `total_adblue_l` for group (and per-vehicle in summary context if low effort)

**Tests (`tests/test_adblue.py`):**

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

**Acceptance criteria:**

- [x] Tractor entries may record optional AdBlue liters
- [x] Non-tractors cannot save AdBlue
- [x] Diesel liters and consumption unchanged
- [x] AdBlue appears in summary totals separately from Kraftstoff liters

---

### Phase 25 — Storage tanks & ledger foundation

**Goal:** CRUD for tanks, deliveries, adjustments; computed stock.

**Files:** `app/models.py`, `app/enums.py`, `app/schemas.py`, `app/services/storage_tanks.py`, `app/services/tank_ledger.py`, `app/routes/storage_tanks.py`, templates, Alembic migration, `tests/test_storage_tanks.py`, `tests/test_tank_ledger.py`.

**Tasks:**

- [x] Models `StorageTank`, `TankLedgerEntry` + migration
- [x] `current_stock_l(db, tank_id)` in `tank_ledger.py`
- [x] Tank CRUD routes + list/detail UI
- [x] Post delivery (+amount) and adjustment (admin, signed, notes required)
- [x] Multiple tanks same `fuel_type` in one group allowed

**Tests (`tests/test_storage_tanks.py`):**

```
test_storage_tank_create_diesel
test_storage_tank_create_second_petrol_tank_same_group_allowed
test_storage_tank_list_scoped_to_active_group
test_storage_tank_detail_404_other_group
test_storage_tank_soft_delete_hidden_from_list
test_storage_tank_update_name_and_capacity
test_storage_tank_delete_requires_admin
test_storage_tank_reader_can_view_not_create
```

**Tests (`tests/test_tank_ledger.py`):**

```
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

**Acceptance criteria:**

- [x] Farm can create multiple Benzin and multiple Diesel tanks
- [x] Stock = opening balance + sum of ledger movements
- [x] Deliveries increase stock; soft-deleted movements excluded

---

### Phase 26 — Fill source & tank selection on fuel entries

**Goal:** Link vehicle fills to a specific farm tank; auto ledger withdrawal.

**Files:** extend `FuelEntry`, `fuel_entries` service/routes/form, `tank_ledger.py`, `tests/test_fuel_fill_source.py`, extend `tests/test_fuel_entries.py`.

**Tasks:**

- [x] Migration: `fill_source`, `fuel_tank_id` on `fuel_entries`
- [x] Default `fill_source=external` for backward compatibility
- [x] Create/update/delete fuel entry syncs `vehicle_withdrawal` ledger row
- [x] Form: tank dropdown filtered by vehicle `fuel_type`; pre-select when exactly one match
- [x] Validation: farm ⇒ tank required; tank fuel type match; cross-group 404

**Tests (`tests/test_fuel_fill_source.py`):**

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

**Acceptance criteria:**

- [x] User chooses which Benzin/Diesel tank when tanking at farm
- [x] External station fills do not affect inventory
- [x] Farm fills reduce the selected tank’s stock
- [x] Legacy entries behave as external

---

### Phase 27 — External withdrawals at farm tanks

**Goal:** Track third-party tanking without polluting fleet stats.

**Files:** `app/routes/storage_tanks.py` (external form), `tank_ledger.py`, `tank_external_form.html`, extend `tests/test_tank_ledger.py`, `tests/test_tank_external.py`.

**Tasks:**

- [x] POST external withdrawal with `recipient_name`, liters, date
- [x] Tank detail shows external rows in ledger
- [x] Dashboard/summary unchanged (no new fuel entries)

**Tests (`tests/test_tank_external.py`):**

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

**Acceptance criteria:**

- [x] External person fills recorded per tank with name
- [x] Inventory correct; fleet statistics unchanged

---

### Phase 28 — Dashboard polish & exports

**Goal:** Operator-facing stock overview and data export.

**Files:** `app/services/dashboard.py`, `app/templates/dashboard.html`, `app/templates/tanks.html`, `app/services/export.py`, `tests/test_dashboard.py`, `tests/test_export.py`.

**Tasks:**

- [x] Dashboard card: tank stock summary (per tank or grouped by fuel type)
- [x] Low/negative stock warning styling
- [x] CSV: extend fuel export; optional `tank-ledger.csv`
- [x] Nav link Tanklager

**Tests:**

```
test_dashboard_shows_tank_stock_when_tanks_exist
test_dashboard_negative_stock_shows_warning
test_dashboard_no_tanks_hides_stock_section
test_export_fuel_entries_includes_fill_source_and_tank_name
test_export_tank_ledger_csv_scoped_to_group
```

**Acceptance criteria:**

- [x] Users see current Hof-Tank levels on dashboard
- [x] Exports reflect new fields

---

## 8. Database migration

Single migration per phase (or one combined migration if phases land in one PR — prefer **one migration per phase** for easier rollback).

**Phase 24:** `fuel_entries.adblue_amount_l`

**Phase 25:** `storage_tanks`, `tank_ledger_entries` tables + indexes:

- `ix_storage_tanks_group_id`
- `ix_tank_ledger_entries_tank_id`
- `ix_tank_ledger_entries_fuel_entry_id` (unique where not null — one ledger row per fuel entry)

**Phase 26:** `fuel_entries.fill_source` (default `'external'`), `fuel_entries.fuel_tank_id` FK nullable

**Backfill:** existing `fuel_entries` get `fill_source='external'`, `fuel_tank_id=NULL`.

---

## 9. Services & file layout

```
app/
  enums.py                    # FillSource, TankMovementType
  models.py                   # StorageTank, TankLedgerEntry; extend FuelEntry
  schemas.py                  # StorageTankCreate/Update, TankLedgerCreate, extend FuelEntry*
  services/
    storage_tanks.py          # CRUD, list for group, list for fuel dropdown
    tank_ledger.py            # current_stock_l, post delivery/external/adjustment,
                              # sync_vehicle_withdrawal_for_fuel_entry
    fuel_entries.py           # call tank_ledger sync on create/update/delete
    fuel_queries.py           # unchanged for fleet scope
    dashboard.py              # tank stock section (Phase 28)
    export.py                 # new columns
  routes/
    storage_tanks.py          # /tanks/*
    fuel_entries.py           # form fields fill_source, fuel_tank_id, adblue
  templates/
    tanks.html, tank_form.html, tank_detail.html, ...
tests/
  test_adblue.py
  test_storage_tanks.py
  test_tank_ledger.py
  test_fuel_fill_source.py
  test_tank_external.py
```

**Transaction boundary:** `create_fuel_entry` / `update` / `soft_delete` and ledger sync must share one DB commit (service-level `db.commit()` once).

---

## 10. Authorization

Reuse `group_page_capabilities` (D-036):

| Action | reader | contributor | admin |
|--------|--------|-------------|-------|
| View tanks & ledger | ✅ | ✅ | ✅ |
| Create/edit tank | ❌ | ✅ | ✅ |
| Post delivery / external | ❌ | ✅ | ✅ |
| Adjustment | ❌ | ❌ | ✅ |
| Delete tank / ledger row | ❌ | ❌ | ✅ |
| Farm fill on fuel entry | ❌ | ✅ | ✅ |

Cross-group IDs: **404** (not 403), matching vehicles/fuel entries (D-035).

Platform support view (D-052): tank routes **read-only** when `platform_view` active — same as fuel list.

---

## 11. CSV export & profile data export

**Status:** ✅ Implemented

- `GET /export/fuel-entries.csv` — `fill_source`, `fuel_tank_name`, `adblue_amount_l`
- `GET /export/tank-ledger.csv` — all ledger rows for group (includes rows for soft-deleted tanks)
- `GET /profile/export/data.json` — user's fuel entries (with new fields) and tank ledger entries they created

---

## 12. Open decisions (for DECISION_LOG)

Record as **`D-054`–`D-058`** when implementing:

| ID | Decision |
|----|----------|
| **D-054** | Negative tank stock allowed; UI shows warning (no hard block) |
| **D-055** | `fill_source` defaults to `external`; farm fill requires explicit tank selection |
| **D-056** | Multiple `StorageTank` per `(group, fuel_type)`; no uniqueness constraint |
| **D-057** | `vehicle_withdrawal` ledger rows synced from `FuelEntry`; not edited directly |
| **D-058** | AdBlue logged on `FuelEntry` only; no AdBlue inventory in v1 |

---

## 13. Implementation pitfalls

1. **Forgetting to sync ledger on fuel entry edit** — test update paths exhaustively (Phase 26 tests).
2. **Using `fuel_amount_l` for AdBlue in consumption** — keep consumption tuples unchanged (Phase 24 test).
3. **Tank dropdown not filtered by fuel type** — car with petrol must not show diesel tanks.
4. **Pre-select hiding validation** — single tank pre-select must still submit `fuel_tank_id` in POST body.
5. **Double deduction** — guard `fuel_entry_id` unique on ledger; update in place, never duplicate withdrawal rows.
6. **Soft-delete drift** — deleting fuel entry must soft-delete ledger; restoring (if ever added) must restore both.
7. **Statistics regression** — external withdrawals must never create `FuelEntry`; add explicit dashboard/summary tests (Phase 27).
8. **Group scoping** — denormalized `group_id` on ledger must match tank on every write (D-003).
9. **Import script** — update `scripts/import_fuel_entries.py` optionally to map external people to ledger API later (out of scope unless user requests).

---

## Test count estimate

| Phase | New tests (approx.) |
|-------|---------------------|
| 24 AdBlue | ~10 |
| 25 Tanks & ledger | ~17 |
| 26 Fill source | ~15 |
| 27 External withdrawal | ~8 |
| 28 Dashboard & export | ~5 |
| **Total** | **~55** |

Run after each phase:

```powershell
python -m pytest -q
ruff check app tests
```
