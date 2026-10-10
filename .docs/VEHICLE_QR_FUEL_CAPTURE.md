# Vehicle QR Labels and Quick Fuel Capture

**Status:** Implemented; physical print and device-scan validation remains a release check.

**Purpose:** Let a farmer scan a printed QR code at a vehicle or fuel station and open a fuel-entry form already bound to that vehicle.

**Related docs:** [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) · [TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md) · [DECISION_LOG.md](./DECISION_LOG.md)

## 1. Problem and outcome

Today, a farmer must navigate to a new fuel entry and choose the vehicle before entering the fill details. That is avoidable effort when the farmer is already standing at the vehicle or pump.

The feature should let a farmer:

- Print a QR label for one vehicle or print labels for all active vehicles in a farm.
- Scan a label and land in Tankly's existing fuel-entry workflow with the correct vehicle fixed in place.
- Save a normal fuel entry for that vehicle in its farm, without being able to accidentally or maliciously substitute a different vehicle.
- Keep the user's active farm unchanged, even when the scanned vehicle belongs to another farm where the user is authorized.

The QR code is a shortcut to an authenticated workflow. It is not a credential and does not grant access by possession of the printed label.

## 2. Current behavior and constraints

- `GET /fuel/new` loads active vehicles for the session's active group. `POST /fuel/new` resolves the submitted vehicle in that same group. See [fuel_entries.py](../app/routes/fuel_entries.py).
- Fuel creation is already implemented in [fuel_entries.py service](../app/services/fuel_entries.py). It accepts an explicit `group_id` and vehicle and verifies that they match before creating the entry.
- The create form is a multi-step mobile capture flow. Vehicle selection and fill-source selection currently share the first step. See [fuel_entry_form.html](../app/templates/fuel_entry_form.html).
- Vehicle list capabilities are group-scoped, and contributors can edit/create while readers cannot. See [vehicles.py](../app/routes/vehicles.py) and [membership.py](../app/services/membership.py).
- A user may belong to multiple farms. The active farm is stored in the signed session; current `get_active_group` routes are intentionally scoped to that farm.
- Unauthenticated requests currently redirect to `/login`, and successful login redirects to `/dashboard`. The QR destination will need a safe return-after-login path.
- `BASE_URL` already exists in [config.py](../app/config.py). It is the appropriate canonical origin for printable links; the request `Host` header should not be trusted to construct permanent QR destinations. Production QR links require HTTPS; local development may use HTTP.
- There is no QR-generation dependency today. This feature does not need a database model or migration if the code is generated from the vehicle's existing IDs.

## 3. Proposed user experience

### Print labels

On the **Vehicles** page, add a **QR-Etiketten drucken** action in the page header, near **Fahrzeug hinzufügen**. This prints labels for all active vehicles in the currently selected farm. Add a small QR/print action to each vehicle row beside its existing edit/delete actions; this opens a print preview for that one vehicle. Both actions are available only to users allowed to create fuel entries.

The print-preview page should show the farm name, a **Drucken** button, and a back link on screen. Those controls disappear on paper. For the first release, use standard A4 paper with a two-column grid of cut-out labels; the fleet sheet continues onto additional pages as needed. Avoid committing to a particular adhesive-label brand or stock until farmers ask for it.

Each label should be black on white and contain a high-contrast QR with its quiet zone, the farm name, vehicle name, and a distinguishing detail such as type/fuel. This keeps a cut-out label identifiable on its own. The browser's native print dialog is sufficient for the first release; do not save generated QR images in the database.

### Scan and capture

1. A QR opens a vehicle-specific URL, proposed as `/fuel/quick/{group_id}/{vehicle_id}`.
2. If the farmer is signed out, Tankly asks them to sign in and then returns them to that exact URL.
3. Tankly resolves the live farm and vehicle, verifies the farmer's membership and contributor-or-higher role in that farm, and renders the capture form with the farm and vehicle clearly named and the vehicle fixed. This QR request uses the target farm as request context only; it does not change the signed session's active farm.
4. The farmer still chooses the fill source. In particular, a farm-sourced fill may require choosing a compatible storage tank. The QR must not silently choose a tank or bypass existing fuel validation.
5. Scanning alone does not create or mutate anything. On submit, Tankly repeats the vehicle, membership, role, and group checks, then creates the entry through the existing fuel-entry service. It redirects back to the QR-specific capture page with a success message and cleared entry fields, preserving the target vehicle context without changing the active farm.

Readers may view other farm data but cannot create fuel entries, so scanning a capture QR as a reader must not grant extra capability. Show the existing access-denied experience for a member with insufficient role. Return not found for unknown, deleted, or non-member farm/vehicle combinations to avoid revealing another farm's assets.

The QR feature adds no side effect of its own beyond the normal fuel-entry workflow. In Tankly, an external-station fuel entry creates the fuel entry; a farm-sourced entry also creates/synchronizes the linked tank-ledger withdrawal so stock stays correct. Do not bypass or duplicate that existing behavior.

## 4. Proposed design decisions and tradeoffs

The user has confirmed the product decisions for farm context and print scope. The remaining rows describe implementation choices to follow unless later review changes them.

| Decision | Why this is recommended | What can go wrong with the alternative |
|---|---|---|
| Encode a canonical, vehicle-specific application URL. | Camera apps can open it directly, and the route can resolve current vehicle data at scan time. | Encoding only an integer requires an extra manual lookup; encoding form data makes the code brittle and risks trusting client-provided values. |
| Require a Tankly session and target-farm membership. | A QR label is visible to anyone near the vehicle. Existing group membership and contributor roles remain the security boundary. | A bearer token or public POST link lets anyone holding or photographing the label create farm records. Numeric IDs are identifiers, not secrets. |
| Revalidate everything on POST and use the route's vehicle ID as the authoritative vehicle. | GET state and hidden form fields can be modified or become stale. Existing service validation remains the final domain guard. | Trusting the preselected form field permits vehicle substitution or cross-farm writes. |
| Keep the saved active-farm selection unchanged when a QR targets another farm; scope the QR request to the target farm. | Scanning a sticker should not silently change the farmer's persisted last-active farm. The URL contains both farm and vehicle IDs, and both must be checked together. | Requiring the active farm to match makes valid labels fail until the farmer manually switches farms. Silently switching farms changes later navigation and the remembered group unexpectedly. |
| Carry target-farm context through GET, POST, and the post-save redirect. | A cross-farm scan must not render the target vehicle with the old farm's tanks/navigation or redirect to the old farm's fuel list. | Scoping only the initial GET creates confusing or unsafe behavior on submit. |
| Build QR URLs from configured `BASE_URL`, requiring HTTPS in production. | The printed link must point to the canonical deployment, independent of proxy/request host headers, and login credentials must never travel over HTTP in production. Local development can use HTTP. | Deriving the origin from an untrusted host can print a poisoned URL; using a relative URL produces an unscannable code; accepting production HTTP exposes sign-in credentials. |
| Generate QR SVGs on the server with the free, open-source Python library Segno. | Segno is pure Python, has no dependencies of its own, emits SVG locally, and is distributed under the 3-Clause BSD license. There is no paid API, per-code charge, or runtime call to a QR provider. | Tankly still owns the normal cost of pinning and updating one package. Raster output can blur when resized; external QR services can log URLs, fail, or charge per use. Hand-written QR encoding is unnecessary and error-prone. |
| Generate labels from current vehicle records; store no QR image or token. | Vehicle IDs and group ownership already exist, and a URL can be regenerated at any time. No migration or cleanup process is needed. | Persisted images/tokens can become stale after renames, deletions, domain changes, or key rotation. |
| Print all vehicles and one vehicle using the same label template. | One implementation supports both a fleet sheet and replacement labels. | Separate implementations tend to drift in content, dimensions, and behavior. |

### Segno license

Segno is free to use, including in a commercial application, under the 3-Clause BSD license. It does not require Tankly to open-source Tankly's own code and does not charge per generated QR code. The license conditions are:

- Keep the copyright notice, license conditions, and disclaimer in source redistributions.
- Reproduce those notices in documentation or other materials with binary redistributions (for example, Tankly's deployed package/container notices).
- Do not use the author's or contributors' names to endorse Tankly without permission.

The license also provides the software "as is" without warranty and limits the authors' liability. Keep Segno's license text with the dependency/license notices and confirm packaging includes it. See the [Segno license](https://github.com/heuer/segno/blob/master/LICENSE) and [PyPI project page](https://pypi.org/project/segno/).

### Multi-farm context is the main implementation wrinkle

The current `get_active_group` dependency and `require_role` check operate on the session's active farm. The proposed QR route is deliberately addressed by target farm and vehicle, so it must not accidentally reuse those dependencies as if the active farm were the QR farm.

Use a centralized group-specific authorization helper (or extend the existing dependency pattern) to check the target `UserGroup` role. Do not hand-roll role comparisons in the route. Build the form's tank data and page context from the target farm. Keep the persisted session's `active_group_id` unchanged, but make the target farm apparent in the capture page. Preserve that target URL through POST/redirect/GET.

This behavior is a confirmed product requirement. Automatically switching farms is out of scope: it would alter the user's active/remembered farm and could redirect subsequent navigation to a different farm. The QR request must be scoped to the target farm from start to finish, while leaving the session's active group untouched.

## 5. Implementation shape

No schema change is proposed.

| Area | Proposed responsibility |
|---|---|
| `app/routes/fuel_entries.py` | Add GET/POST QR capture routes. Resolve the explicit target farm and vehicle, require target-farm contributor access, reuse the existing form and `fuel_entry_service.create_fuel_entry`, then redirect to the same QR capture URL. |
| `app/dependencies.py` or a focused authorization helper | Reuse the central role hierarchy for a supplied target group. Keep route code free of ad hoc role comparisons. Preserve 404 behavior for unknown/non-member targets. |
| `app/routes/vehicles.py` | Add the contributor/admin-protected print view and per-vehicle QR image response, scoped to the active farm for printing. |
| `app/services/vehicle_qr.py` | Build an absolute QR destination from `BASE_URL` plus validated farm/vehicle IDs and render SVG. Translate only Segno's expected `DataOverflowError` to `QrGenerationError`; leave unexpected errors for the global handler. |
| `app/templates/vehicles.html`, `_macros.html` | Add print actions without changing the existing vehicle CRUD workflow. Show them only to users with create capability. |
| `app/templates/vehicle_qr_labels.html` (new) | Render one or many labels and print-only layout. Use the live vehicle name/type as text. |
| `app/templates/fuel_entry_form.html` | Support a QR capture mode with a locked vehicle display, correct form action, and the existing fill-source and validation behavior. Do not accept a client-selected replacement vehicle in this mode. |
| `app/routes/auth.py`, `app/templates/login.html` | Preserve a QR destination across login. Accept only a safe local path (or a narrowly allowlisted QR route); reject absolute URLs, protocol-relative paths, and malformed destinations to prevent open redirects. |
| `requirements-prod.txt` | Add Segno as a pinned runtime dependency; `requirements-dev.txt` includes production requirements already. Document why in `DECISION_LOG.md` before adding a package, per repository rules. Segno itself has no runtime dependencies. |

If `BASE_URL` is empty or malformed, do not generate relative or request-host QR links. Hide/disable label printing with a clear setup error. Require an HTTPS origin in production; local testing may use HTTP and should configure a URL reachable from the scanning device (`localhost` on the developer's computer is not reachable from a phone).

Segno's expected payload-overflow error becomes an application-level `QrGenerationError`; the SVG route logs it and returns a controlled 503 with a setup-oriented message. Do not catch arbitrary exceptions around QR generation: unexpected defects must reach the existing global handler, which logs them and returns a 500.

## 6. Security and failure cases

- The QR URL is public-facing text. Never put credentials, session IDs, one-time login tokens, or authorization claims in it.
- Validate that the live group owns the live vehicle from the same request path. A valid group ID paired with a vehicle from another group must fail.
- Recheck membership and contributor role on both GET and POST; membership may be revoked while a form is open.
- Validate any selected storage tank against the target farm and vehicle fuel type using existing service logic.
- Keep the existing global CSRF protection on POST. The QR GET and SVG GET must not mutate data.
- Validate the login `next` destination as local/allowlisted. Never redirect to an arbitrary URL supplied in a query or hidden field.
- Deleted vehicle, deleted farm, invalid pair, or non-member: no form and no data disclosure. Insufficient role: no creation capability.
- If a vehicle is renamed, the QR still resolves by ID but printed name text is stale; provide a reprint action. If a vehicle is deleted, its printed code becomes unusable.
- A deployment-domain change invalidates old printed links. Confirm `BASE_URL` before printing production labels and keep the route stable after release.
- Generate codes only for active vehicles in the requested farm. Do not let an optional `vehicle_id` query parameter escape that farm's scope.

## 7. Test-first implementation plan

Follow the repository's Red -> Green -> Refactor workflow. Add tests before implementation and confirm they fail for the intended reason.

1. **QR URL and rendering:** configured base URL produces the expected absolute QR destination; missing base URL is handled safely; SVG is valid and encodes the intended URL. Segno overflow becomes a controlled error; unexpected failures use global 500 handling. No external QR service is called.
2. **Print view:** contributor/admin can print one active vehicle or all active vehicles in the active farm; deleted and other-farm vehicles are excluded; readers cannot access label generation.
3. **Capture GET:** valid member contributor/admin sees the correct locked vehicle and target farm; reader is denied; anonymous scan preserves the destination through successful login; wrong group/vehicle pair, deleted records, and non-member return not found.
4. **Capture POST:** valid values create exactly one entry with the route's vehicle, target group, and session user; the response is a 303 back to the QR route with success feedback; submitted vehicle substitution cannot change the target.
5. **Isolation and invariants:** a user active in Farm A but scanning a vehicle in Farm B can capture only if they are a contributor/admin of B; the saved entry belongs to B; the persisted active group remains A. A user with no B membership cannot read or write B's data.
6. **Existing safeguards:** invalid amounts/dates, incompatible farm tank, invalid CSRF, and insufficient role still fail through the existing validation/security behavior.
7. **Login redirect safety:** local QR destination is retained; absolute and protocol-relative destinations are rejected; a failed login preserves only the safe destination.
8. **Quick-submit invariants:** reader POST, invalid CSRF, target-farm membership revoked after GET, vehicle deleted after GET, foreign-farm tank, and wrong-fuel-type tank all fail without creating a fuel or ledger row.
9. **URL configuration:** reject malformed IPv6 authorities, invalid/out-of-range/zero ports, credentials, paths, query/fragment values, and production HTTP; allow local development HTTP.

After the focused tests pass, run the full pytest suite and `ruff check app tests`; run `ruff format --check app tests` if that is the repository's configured CI check. Check the printed layout in a browser at mobile width and in print preview, including a long vehicle name and a multi-page fleet sheet.

## 8. Acceptance criteria

- A contributor/admin can print a single vehicle label and a sheet of all active vehicles for the current farm.
- Scanning an active label on a phone opens the intended vehicle's fuel form, with no manual vehicle selection.
- A logged-out farmer can sign in and continue to that QR destination safely.
- Fuel-source and tank validation remain intact; creating an entry requires normal authentication, target-farm membership, contributor-or-higher role, and CSRF.
- A QR cannot create an entry for another vehicle or farm by tampering with the form or URL.
- Scanning a QR from another farm does not silently change the user's persisted active farm (pending product confirmation).
- Labels are readable and scannable in print preview and use a canonical configured deployment URL.
- No database migration is required; new runtime dependencies and architectural decisions are documented.

## 9. Release check

The first release uses a standard A4 two-column cut-out layout; it does not target a particular adhesive label-sheet brand. Before release, print a sample and scan it with supported phone camera apps. Confirm QR quiet zones, text fit, multi-page breaks, and that the phone opens the expected canonical Tankly URL.

The cross-farm behavior, individual and fleet print options, and Segno dependency are implemented and recorded in [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) and [DECISION_LOG.md](./DECISION_LOG.md). No migration is required.