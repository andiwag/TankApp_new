# Tankly interface system

Locked after craft review (2026-07-22). Apply on authenticated farm UI (`.t-lean` / `.t-dashboard`). Auth, marketing, and platform shells align later.

## Intent

- **Who:** Hof operator / driver between jobs — often mobile, sun glare, gloves.
- **Verb:** Log a tanking now; secondarily trust tank stock and due maintenance.
- **Feel:** Field instrument / yard clipboard — calm, dense, material, trustworthy. Not startup dashboard.

## Domain

Hof-Tank, Zapfsäule, Literstand, Bestandsbuch, AdBlue, Schlepper-Stunden, Lieferung, Inventur, Verbrauch.

## Signature

**Tank level as visual language.** Capacity fill bars wherever liters appear (dashboard stock, tanks list, tank detail hero). Without the gauge, the UI should no longer read as Tankly.

## Rejected defaults

| Default | Replacement |
|---------|-------------|
| Inter + cool slate SaaS | IBM Plex Sans + soil/steel/diesel tokens |
| Equal KPI strips as identity | Attention + tank gauge; metrics demoted |
| Chip-decorated list cards | Logbook rows; chips rare (one status max) |

## Direction

- **Depth:** Borders only (no lift shadows on panels). Menus may use one quiet shadow for elevation above plate.
- **Spacing base:** 4px grid; component pad 12–16px; section gaps 16–20px.
- **Radius:** 8px surfaces/controls (`--dashboard-radius` / `--radius`).
- **Type ratio:** ~1.25 from 14px body. Hierarchy via weight + color more than size.
- **Accent:** One enamel green for primary action / active nav. Amber = diesel warning. Red = fault. AdBlue blue only for AdBlue semantics.
- **Density:** Workbench-tight on lists and capture; slightly airier on analytics.

## Tokens (primitives)

| Token | Role | Value |
|-------|------|-------|
| `--yard` | Canvas | `#ebece8` |
| `--plate` | Surface | `#f7f7f5` |
| `--plate-inset` | Subtle / inputs | `#f0f1ee` |
| `--seam` | Border | `rgba(26, 31, 28, 0.10)` |
| `--ink` | Primary text | `#1a1f1c` |
| `--mist` | Muted text | `#5c6560` |
| `--enamel` | Brand / primary | `#0d6b4f` |
| `--enamel-hover` | Primary hover | `#0a5840` |
| `--diesel` | Warning | `#b45309` |
| `--fault` | Danger | `#b91c1c` |
| `--adblue` | AdBlue only | `#1d4ed8` |

Compat aliases: `--tankly-*` and `--dashboard-*` map to these primitives.

## Typography

- **Family:** IBM Plex Sans (400/500/600/700), system fallbacks after.
- **Tabular nums** on all dynamic liters, costs, stands, gauges.
- **Optical:** Headings slight negative tracking; body ~1.5 line-height.

## Key patterns

### Tank gauge (`t-tank-gauge`)

- Track inset on plate; fill enamel (fault tone when negative stock).
- Sizes: `sm` (list rows), `md` (dashboard), `lg` (tank detail hero).
- Omit fill bar when `capacity_l` unknown; still show liters as text.
- `aria` label includes percent or “Kapazität unbekannt”.

### Page header

- Title + one subtitle; one primary action; secondary in menu.

### Panel

- `--plate` fill, `--seam` border, 8px radius, no shadow.

### List row

- Title / meta / liters; optional one status chip; optional `sm` gauge.

## Roadmap (remaining)

Craft roadmap complete for farm + auth shells. Landing/legal intentionally unchanged.

### Auth shell + motion (done)

- Login/register/forgot/reset + error: `.t-auth` / `.t-auth-panel` (no emoji, no glass)
- Landing + legal pages left on `marketing_base` as-is
- Motion: `.t-motion-enter`, capture step enter, menu panel; respects `prefers-reduced-motion`
- Empty/error alerts use domain tokens (`.t-empty-state`, `.t-form-alert`)


### Analytics narrative (done)

- `/analytics`: one `.t-analytics-story` hero per view; charts secondary
- Desktop: 12-month liters story + `.t-analytics-facts` (no equal KPI strip)
- Mobile tabs keep one story each; instrument `.t-trend-delta` (no pill chips)
- Charts: IBM Plex Sans + enamel/diesel domain colors


### Tank cockpit (done)

- `/tanks/{id}`: one `.t-tank-cockpit` hero (stock number → gauge → capacity meta)
- Primary **Lieferung erfassen**; secondary actions in **Weitere Aktionen**
- Ledger: movement type as text; signed liters via `.t-tank-ledger-amount--in/out`

### Capture-first fuel (done)

- Create mode: mobile 3-step yard flow (`Fahrzeug` → `Liter` → `Fertig`) via `.t-capture-flow`
- Hero liter/stand inputs: `.t-capture-input--hero`
- Create uses flat `.t-capture-surface` / `.t-capture-block` (no nested form cards)
- Desktop create: all steps visible; edit stays single scroll

### Nav IA (done)

- Mobile primary: Dashboard · Tanken · + · Tanks · Mehr
- Fahrzeuge moved into Mehr; Tanklager removed from Mehr
- Desktop order: Dashboard → Tankvorgänge → Tanklager → Fahrzeuge → …

### List craft (done)

- One status chip max (Teilbefüllung / Negativer Bestand only)
- Vehicle/tank type as meta text; AdBlue/Hof/Voller Tank as meta