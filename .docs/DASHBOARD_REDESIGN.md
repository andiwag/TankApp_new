# Dashboard Redesign Implementation Plan

**Status:** ✅ Complete  
**Scope:** Authenticated farm dashboard at `/dashboard`  
**Primary files:** `app/templates/dashboard.html`, `app/static/app.css`, `app/static/dashboard.js`, `app/services/dashboard.py`, `app/routes/dashboard.py`  
**Related decisions:** D-032, D-036, D-038, D-063  

## 1. Outcome

Redesign the dashboard as a lean operational cockpit that answers four questions in order:

1. Does anything require attention?
2. What happened today and this month?
3. What was recorded recently?
4. Where can the user act next?

The finished dashboard must retain all existing data, authorization, tenant isolation, subscription entitlements, links, empty states, and mobile navigation behavior. The work changes presentation and removes redundant dashboard-only data; it does not add a model, migration, route, package, or new product feature.

## 2. Goals

- Establish a clear visual hierarchy instead of presenting every item as an equal card.
- Keep one dominant create action for users who may edit: `Tankvorgang erfassen`.
- Put overdue maintenance and negative tank stock ahead of routine information.
- Show metrics and the beginning of recent activity in the first desktop viewport.
- Reduce mobile scrolling before recent activity without reducing touch-target sizes.
- Make charts useful but secondary; keep them off the mobile dashboard.
- Introduce dashboard primitives that can later be adopted by other authenticated pages.
- Preserve correct behavior for admin, contributor, reader, free-tier, paid-tier, empty, and platform support-view states.

## 3. Non-goals

- Redesigning the sidebar, mobile bottom navigation, add sheet, or another page.
- Adding new dashboard metrics, trends, low-stock thresholds, notifications, or preferences.
- Changing consumption, cost, inventory, reminder, soft-delete, or group-scoping rules.
- Adding vehicle images or changing the vehicle data model.
- Introducing a frontend framework or replacing Jinja, Alpine, Tailwind runtime utilities, or Chart.js.
- Making a global card or macro change that silently restyles unrelated pages.

## 4. Current Behavior That Must Survive

### Data

- Active, non-deleted vehicle count.
- Current-month fuel-entry count and cost.
- Today's fuel-entry count.
- Five most recent active fuel entries, including vehicle, date, cost, and consumption when available.
- Thirty-day consumption points and six-month cost totals.
- Current stock for every active storage tank, including negative-stock warning state.
- Maintenance reminders and computed days until due.
- Personalized, time-dependent greeting.

### Security and entitlements

- Unauthenticated users redirect to `/login`.
- Users without an active group redirect to `/groups`.
- Every query remains scoped to the active group.
- Fuel entries tied to deleted vehicles remain excluded.
- Readers never receive create links.
- Contributors and admins retain the fuel-entry create action.
- Maintenance and analytics links respect group feature availability.
- CSV export remains visible to entitled readers as well as editors.
- Platform support view remains read-only and keeps its global banner.

### Navigation and actions

- Vehicle metric links to `/vehicles`.
- Fuel metric and recent activity link to `/fuel`.
- Cost links to `/analytics` when enabled and falls back to `/fuel` otherwise.
- Maintenance links only when the feature is enabled.
- Tank inventory links to `/tanks`.
- Desktop secondary actions preserve maintenance create, vehicle create, and CSV export subject to permissions.
- Mobile keeps the existing status-row destination, bottom navigation, and add sheet.

## 5. Target Information Architecture

### Desktop (`lg` and above)

1. **Page header**
   - Greeting and short daily context on the left.
   - Primary fuel-entry action on the right for editors.
   - `Weitere Aktionen` menu beside it when at least one permitted secondary action exists.
   - Readers see no primary create action; entitled export remains available in the secondary menu.

2. **Attention strip**
   - Render only when there is negative tank stock or a due/overdue maintenance reminder.
   - Negative stock uses danger styling and links to tank inventory.
   - Overdue maintenance uses danger styling; upcoming maintenance uses warning styling.
   - Order: negative stock, overdue maintenance, upcoming maintenance.
   - Do not invent a low-stock warning because tank capacity and thresholds are not available.

3. **Metric band**
   - One shared surface containing four metrics: vehicles, monthly fuel entries, monthly cost, maintenance due.
   - Use separators rather than four independent cards.
   - Keep the existing statistic IDs so behavioral tests and selectors remain stable.
   - Values use tabular numerals and never alter the band dimensions.

4. **Primary content grid**
   - Left, wider column: recent fuel activity as a dense desktop table/list with five rows.
   - Right column: one chart panel with `Verbrauch` and `Kosten` segmented controls.
   - The active chart has a visible period/unit label and an independent empty state.

5. **Operational detail grid**
   - Tank inventory as compact rows, not nested cards. Show at most four rows plus a count/link for remaining tanks.
   - Maintenance as compact rows. Show at most three reminders plus `Alle anzeigen`.
   - Omit the former vehicle preview; vehicle count and navigation already provide that route.

### Tablet (`sm` through `lg-1`)

- Keep the mobile shell and navigation.
- Use the compact metric grid.
- Use one content column; no chart canvases.
- Preserve section order from mobile.
- Do not introduce horizontal scrolling.

### Mobile (`sm-1` and below)

1. Brand header and maintenance notification affordance.
2. Greeting with shared dashboard header typography.
3. Lean daily status row (`t-dashboard-status`).
4. Attention section, only when attention is required (before metrics).
5. Compact 2×2 metric band using the same metric cells as desktop (no KPI card tiles).
6. Tank stock, recent activity, and maintenance as shared panel/row primitives (max 3 / 3 / 2).
7. Existing fixed bottom navigation and add sheet.

Charts and the vehicle preview remain absent. The status row continues to link directly to `/fuel/new` for editors with no entries today, `/fuel` for readers, and `/fuel` when entries already exist. Mobile uses the same scoped dashboard tokens as desktop; decorative icon tiles and nested list cards are not used.

## 6. Visual System

### Principles

- Quiet operational UI: information density comes from alignment and grouping, not smaller unreadable type.
- White is reserved for meaningful surfaces; page sections are not all floating cards.
- Green indicates primary action or active navigation, not every decorative icon.
- Amber and red are reserved for actionable warning and danger states.
- Neutral borders carry most structure; shadows are subtle and uncommon.
- Use a maximum `8px` radius for new dashboard surfaces and controls.
- Use icons only when they improve scanning; every icon-only control needs an accessible name and tooltip where its meaning is not obvious.

### Additive tokens

Add semantic custom properties without changing existing tokens used by other pages:

- `--dashboard-canvas`
- `--dashboard-surface`
- `--dashboard-surface-subtle`
- `--dashboard-border`
- `--dashboard-text`
- `--dashboard-muted`
- `--dashboard-accent`
- `--dashboard-warning`
- `--dashboard-danger`
- `--dashboard-radius`

All new selectors must be scoped under `.t-dashboard` or use purpose-specific `t-dashboard-*` names. Do not change `glass_panel`, `kpi_card`, or generic list macros globally during this task.

### Typography

- Use the existing application typography during the dashboard implementation so other pages do not change unexpectedly.
- Remove the blocked Google Fonts import in a separate shell-wide typography task, or self-host the selected font with its license and record that dependency decision.
- Use `font-variant-numeric: tabular-nums` for metrics, dates, costs, liters, and countdowns.
- Do not use viewport-width font scaling or negative letter spacing in new dashboard styles.

## 7. Component and Template Plan

Add focused macros to `_macros.html` only where they remove real duplication:

- `dashboard_metric(...)`: one metric cell with optional destination and stable statistic ID.
- `dashboard_attention_item(...)`: severity, icon, title, detail, and destination.
- `dashboard_inventory_row(...)`: tank name, localized fuel label, quantity, and warning state.
- `dashboard_action_menu(...)`: accessible desktop secondary-action menu.

Keep these existing macros where they already fit:

- `fuel_entry_row` for compact mobile activity.
- `maintenance_reminder_compact` for mobile and narrow layouts after visual tuning.
- `section_link_header` for mobile section headings.
- `empty_state`, with dashboard-specific surrounding layout rather than global changes.

Do not nest dashboard surfaces. Metric cells live inside one band; inventory and maintenance rows live directly inside their section.

## 8. Interaction Wiring

### Secondary action menu

- Use Alpine because it is already loaded by the authenticated shell.
- Trigger exposes `aria-haspopup="menu"` and synchronized `aria-expanded`.
- Menu closes on outside click, Escape, and action selection.
- Keyboard focus moves predictably; focus is returned to the trigger after Escape.
- Render the menu only when at least one permitted action exists.
- Actions:
  - Maintenance create: editor plus maintenance capability.
  - Vehicle create: editor.
  - CSV export: export entitlement, including readers.

### Segmented chart

- Use two real buttons with `role="tab"`, `aria-selected`, and matching `aria-controls`.
- Default to consumption when consumption data exists; otherwise default to cost.
- Create only the initially visible Chart.js instance on load.
- Lazily create the second chart on first activation to avoid hidden-canvas sizing errors.
- Switching tabs must not fetch data or navigate.
- Preserve separate empty messages for missing consumption and cost data.
- Destroy/recreate only if needed for responsive sizing; do not create duplicate chart instances.
- Do not load or initialize charts below `lg`.

### JavaScript organization

- Move dashboard chart setup out of the template into `app/static/dashboard.js`.
- Keep chart data in escaped `application/json` script elements rendered by Jinja.
- Load local `chart.umd.min.js` before `dashboard.js`, both with `defer` in dependency order.
- Guard every DOM lookup so empty and mobile states do not raise console errors.
- Keep all labels and accessible text in the rendered HTML; JavaScript controls behavior only.

## 9. Service and Route Plan

### `app/services/dashboard.py`

- Preserve the active fuel-entry query and all date boundaries.
- Remove `VEHICLES_PREVIEW_LIMIT` and `vehicles_preview` from the returned context after its tests are changed.
- Replace loading all vehicles solely for preview/count with a scoped count query, preserving deleted-vehicle exclusion.
- Keep `recent_entry_rows`, chart arrays, and `tank_stock_rows` contracts.
- Add no low-stock calculation.
- If attention ordering becomes non-trivial, add a small pure helper that accepts tank rows and reminder dictionaries; do not put HTML labels or URLs in the service.

### `app/routes/dashboard.py`

- Keep the handler thin.
- Preserve reminder retrieval and `days_until` calculation unless that calculation is first moved into the reminder service with focused tests.
- Do not add permission checks in the route; continue using capability values from services/dependencies.

No database migration is expected. Stop and reassess scope before implementation if a desired state requires unavailable data such as tank capacity or a user-defined threshold.

## 10. State Matrix

| State | Header/action | Attention | Metrics | Content |
|---|---|---|---|---|
| Admin, paid | Primary action + all allowed secondary actions | Warnings when present | All linked as entitled | Charts, export, maintenance links |
| Contributor, paid | Primary action + permitted secondary actions | Warnings when present | All linked as entitled | No admin-only behavior introduced |
| Reader, paid | No create action; export in secondary menu | Read-only links | Linked only to readable destinations | No `/new` links anywhere |
| Free tier | Create actions per role; no paid-only export | Existing available warnings | Paid feature metrics are non-link or fallback | No hidden-feature dead links |
| Empty group | Fuel create action for editor | Hidden | All zero | Purposeful first-entry empty state |
| No consumption data | Normal | Normal | Normal | Consumption tab has empty message; cost remains usable |
| No cost data | Normal | Normal | Cost is `0,00 €` | Cost tab has empty message; consumption remains usable |
| No tanks | Normal | No tank warning | Normal | Inventory section omitted |
| Negative tank | Normal | Danger item first | Normal | Negative row remains visibly marked |
| No reminders | Normal | No maintenance warning | Maintenance value zero | Maintenance section omitted or compact healthy copy |
| Overdue reminder | Notification present | Danger item before upcoming reminders | Count unchanged | Negative day value renders `überfällig` |
| Long names/values | No overflow | Text truncates with accessible full value | Stable columns | Rows remain aligned |
| Platform support view | No write action | Read-only information | Normal data | Support banner remains unobstructed |

## 11. Test-Driven Implementation Sequence

Each behavior slice follows Red -> Green -> Refactor. Run the named focused test file immediately after each first implementation edit.

### Slice 1: Lock behavioral contracts

Add or update tests before changing production code:

- Dashboard retains stable metric IDs in both responsive render paths.
- Admin and contributor see the primary fuel action.
- Reader sees no `/new` links and still sees entitled CSV export.
- Free tier does not render CSV export or dead paid-feature links.
- Negative stock and overdue maintenance receive distinct attention markers.
- No-attention state does not render an empty attention container.
- Empty group renders zero metrics and an editor/reader-appropriate empty state.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_ui_regression.py -q
```

### Slice 2: Service cleanup

Tests first:

- Vehicle count still excludes deleted vehicles after preview removal.
- Context no longer depends on `vehicles_preview`.
- Existing recent-entry, chart, cost, tank, and capability values are unchanged.

Implementation:

- Change vehicle retrieval to a count query.
- Remove preview constant and context key.
- Update seed/dashboard tests that explicitly assert preview data.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_seed_dev.py tests/test_polish.py -q
```

### Slice 3: Desktop header and actions

Tests first:

- Exactly one prominent fuel-create action is present for an editor in desktop content.
- Secondary menu includes only permitted actions.
- Reader export remains available without create actions.
- Menu trigger has the required ARIA attributes.

Implementation:

- Add the dashboard wrapper and page header.
- Add the permission-aware Alpine action menu.
- Remove the old four-button quick-action cluster and duplicate notification button.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_ui_regression.py tests/test_mobile_layout.py -q
```

### Slice 4: Attention and metric band

Tests first:

- Negative stock renders danger attention linked to `/tanks`.
- Overdue and upcoming reminders render correct severity and wording.
- Attention ordering is deterministic.
- No warning data omits the section.
- All four metric values and destinations are correct for role/tier combinations.

Implementation:

- Add attention markup/macros.
- Replace desktop KPI cards with the shared metric band.
- Tighten mobile metric tiles without changing their behavior.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_mobile_design.py tests/test_ui_regression.py -q
```

### Slice 5: Activity, inventory, and maintenance

Tests first:

- Desktop activity keeps five-entry service limit and newest-first ordering.
- Mobile shows the first three entries.
- Inventory caps visible rows and exposes a route to all tanks.
- Negative inventory retains warning text and class/hook.
- Maintenance caps visible rows and preserves due wording.
- Vehicle preview is absent.

Implementation:

- Build the primary activity section.
- Convert tank cards to rows.
- Convert desktop maintenance cards to rows.
- Remove the vehicle-preview section.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_mobile_design.py tests/test_tank_ledger.py -q
```

### Slice 6: Unified chart

Tests first:

- One chart region exposes two tabs and two controlled panels.
- Escaped JSON payloads for both datasets are present.
- Script assets are loaded in dependency order.
- Each no-data message is rendered and associated with its panel.
- Mobile chart container remains hidden/not initialized.

Implementation:

- Add `dashboard.js`.
- Replace two chart cards with one tabbed chart section.
- Add lazy initialization and responsive guard.
- Remove the inline dashboard script.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_mobile_design.py tests/test_vendor_assets.py -q
```

Then verify in the browser that both tabs display correctly and that no console errors occur at desktop or mobile widths.

### Slice 7: Responsive styling and edge cases

Tests first where server-rendered hooks can express the contract; use browser validation for actual layout:

- Stable responsive wrappers exist.
- Long labels have truncation/full-title behavior.
- Icon-only controls have accessible names.
- Existing mobile bottom navigation and add sheet remain in the response.

Implementation:

- Add scoped dashboard CSS and additive tokens.
- Finalize desktop, tablet, mobile, focus, hover, active, and reduced-motion states.
- Bump the `app.css` cache query in `base.html` once, after styles stabilize.

Run:

```powershell
python -m pytest tests/test_dashboard.py tests/test_mobile_design.py tests/test_mobile_layout.py tests/test_ui_regression.py -q
```

## 12. Accessibility Checklist

- One `h1`; section headings follow a logical `h2` hierarchy.
- Landmarks and sections have meaningful accessible names where needed.
- All interactive metric cells are anchors; noninteractive metrics are not styled as links.
- Action-menu and chart-tab keyboard behavior is complete.
- Focus indicators have at least 3:1 contrast and are never clipped.
- Text and meaningful icons meet WCAG AA contrast.
- Warning meaning is conveyed by text/icon as well as color.
- Chart canvases have accessible summaries or nearby textual context; the canvas is not the only representation of critical data.
- Touch targets are at least 44 by 44 CSS pixels on mobile.
- Layout remains usable at 200% zoom and 320px width.
- Reduced-motion users do not receive scale or transition effects that impede use.

## 13. Performance and Reliability Checklist

- Preserve or improve the dashboard query count covered by `test_no_n_plus_1_queries_on_dashboard`.
- Do not add per-row queries for tanks, reminders, vehicles, or recent entries.
- Use a count query instead of loading vehicles removed from the UI.
- Keep Chart.js local; no CDN dependency.
- Initialize charts only on desktop and only when their tab is used.
- Do not fetch dashboard data client-side; retain server-rendered first paint.
- No JavaScript errors for empty arrays, absent sections, readers, or mobile layouts.
- Avoid cumulative layout shift by giving the chart and metric band stable dimensions.
- Preserve CSP compatibility; do not add a remote font, script, image, or style origin.

## 14. File-Level Change Map

| File | Planned change |
|---|---|
| `tests/test_dashboard.py` | New hierarchy, attention, metrics, service cleanup, chart-data tests |
| `tests/test_ui_regression.py` | Permission and action-menu affordances |
| `tests/test_mobile_design.py` | Compact dashboard structure and preserved mobile behavior |
| `tests/test_mobile_layout.py` | Replace obsolete class-string assertions with stable dashboard hooks |
| `tests/test_seed_dev.py` | Remove obsolete vehicle-preview context assertion if present |
| `app/services/dashboard.py` | Count vehicles without preview; preserve remaining context |
| `app/routes/dashboard.py` | Expected to remain thin; only reminder normalization if justified by tests |
| `app/templates/_macros.html` | Add focused metric, attention, inventory, and action-menu macros |
| `app/templates/dashboard.html` | Replace desktop/mobile composition and JSON script payloads |
| `app/static/dashboard.js` | Accessible chart tabs and lazy Chart.js initialization |
| `app/static/app.css` | Scoped dashboard tokens, layout, states, and responsive rules |
| `app/templates/base.html` | One final CSS cache-version bump only |
| `.docs/DEVELOPMENT_PLAN.md` | Add/check redesign work item after implementation |
| `.docs/DECISION_LOG.md` | Update only if implementation introduces an architectural or dependency decision |

## 15. Browser Validation Matrix

Use the deterministic `Hof Winkling` seed and also construct targeted test states.

| Viewport | Required checks |
|---|---|
| 390 x 844 | No horizontal overflow; fixed nav clear; compact metrics; attention order; recent activity reachable; long values fit |
| 768 x 1024 | Tablet single-column layout; no chart initialization; touch targets; no awkward card stretching |
| 1024 x 768 | Desktop transition; action menu and metric band fit; support banner does not overlap |
| 1280 x 800 | Metrics and beginning of activity visible in first viewport; both chart tabs work |
| 1440 x 1000 | Balanced max-width composition; inventory and maintenance alignment; no excessive empty space |
| 200% zoom | Navigation, menus, metric values, and headings remain usable without overlap |

For desktop and mobile:

- Capture populated, empty, reader, negative-stock, and overdue-maintenance screenshots.
- Exercise every visible link and action destination.
- Open/close the secondary menu with pointer, Escape, and keyboard navigation.
- Switch chart tabs repeatedly and resize after each tab has initialized.
- Confirm no failed local assets, console exceptions, inaccessible names, overlap, or blank canvas.
- Confirm canvas pixels are nonblank for datasets with values.

## 16. Final Validation

Run formatting before the final test suite:

```powershell
ruff format app tests
ruff check app tests
python -m pytest -q
```

Review the final diff to ensure unrelated pages and generic macros were not restyled. Record the actual test count in the completion report.

## 17. Definition of Done

- All target desktop, tablet, and mobile compositions are implemented.
- Primary and secondary actions are correctly wired for every role and tier.
- Every metric and section links to the correct existing destination.
- Attention states are accurate, ordered, and absent when not needed.
- Recent activity, inventory, maintenance, chart tabs, empty states, and notification affordances work with real seeded data.
- No migration, remote asset, package, dead link, duplicate action, hidden create link, or client-side data fetch was introduced.
- Dashboard query count does not regress.
- Keyboard, screen-reader, contrast, zoom, overflow, reduced-motion, and touch-target checks pass.
- Browser checks pass at all specified viewports with no console errors or blank charts.
- Focused tests, Ruff, and the full pytest suite pass.
- Development plan and decision log are updated only as warranted.
- Completion report lists changed files, tests added, full-suite result, browser matrix result, and any documented decision.

## 18. Recommended Delivery Order

Deliver this as one feature branch but in small reviewable commits if the user later requests commits:

1. Test contracts and service cleanup.
2. Header, action menu, attention strip, and metric band.
3. Activity, inventory, and maintenance composition.
4. Chart interaction and external dashboard script.
5. Responsive polish, accessibility, documentation, and final validation.

Do not begin a broader authenticated-shell or second-page redesign as part of this work. The dashboard primitives should prove the visual language first; later page migrations can adopt them deliberately.