# Tankly – Stripe Billing Implementation Guide

Step-by-step checklist for integrating **Stripe Checkout + Billing + Tax** into Tankly. Billing is **per Group** (farm/business), not per user. The existing `Group.subscription_tier` column becomes a denormalized cache updated from webhooks.

**Status:** Implemented (Phase 23). Go-live steps: [STRIPE_GO_LIVE.md](./STRIPE_GO_LIVE.md).

**Prerequisites:** Landing page live (`/`), legal pages filled in (`/impressum`, `/datenschutz`, `/agb`), Steuerberater consulted. Operator support tooling: [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md) (Phase 22).

**Partner tier:** `partner` is a **non-Stripe** complimentary tier (same feature limits as `farm`). It is granted/revoked only by platform admins via `/platform/farms/{id}` — never via Checkout. Rows stay without `stripe_subscription_id`, so webhooks/reconcile do not overwrite them. Do not fake a paid `farm`/`pro` tier for gifted farms.

---

## Table of contents

1. [Business & legal prep (Austria)](#1-business--legal-prep-austria)
2. [Stripe Dashboard setup](#2-stripe-dashboard-setup)
3. [Environment variables](#3-environment-variables)
4. [Database schema](#4-database-schema)
5. [Application architecture](#5-application-architecture)
6. [Implementation phases & checklist](#6-implementation-phases--checklist)
7. [Webhook handling](#7-webhook-handling)
8. [Entitlements & feature gating](#8-entitlements--feature-gating)
9. [UI integration](#9-ui-integration)
10. [Testing](#10-testing)
11. [Production go-live checklist](#11-production-go-live-checklist)
12. [Bookkeeping (sevDesk / Billflow)](#12-bookkeeping-sevdesk--billflow)

---

## 1. Business & legal prep (Austria)

Complete **before** enabling live Stripe charges.

### Steuerberater meeting (1×, ~1 hour)

- [ ] Confirm legal form (Einzelunternehmen, GmbH, …)
- [ ] Kleinunternehmer vs. reguläre USt-pflichtig
- [ ] UID-Nummer vorhanden / beantragen
- [ ] **Union OSS** registrieren wenn B2C-Verkäufe in andere EU-Länder > €10.000/Jahr erwartet
- [ ] Reverse Charge für B2B-Kunden mit gültiger UID
- [ ] Rechnungsnummernkreis und Aufbewahrung (7 Jahre)

### Legal pages (required before paid launch)

- [ ] `/impressum` – echte Firmendaten (keine Platzhalter)
- [ ] `/datenschutz` – AVV mit Stripe, Hosting, E-Mail; DSGVO-konform
- [ ] `/agb` – Tarife, Kündigung, Haftung, österreichisches Recht
- [ ] Stripe als Zahlungsdienstleister in Datenschutzerklärung erwähnen

### Stripe account

- [ ] Account unter [stripe.com/at](https://stripe.com/at) eröffnen
- [ ] Unternehmensdaten, Bankkonto (EUR), Identitätsprüfung abschließen
- [ ] **Test mode** für Entwicklung nutzen bis Go-Live

---

## 2. Stripe Dashboard setup

### Products & prices (Test mode first)

Create three products matching the landing page:

| Product | Price | Billing | Stripe lookup key (suggested) |
|---------|-------|---------|-------------------------------|
| Tankly Pro | €19.00 | Monthly recurring | `tankly_pro_monthly` |
| Tankly Pro | €190.00 | Yearly (optional) | `tankly_pro_yearly` |
| Tankly Farm | €49.00 | Monthly recurring | `tankly_farm_monthly` |
| Tankly Farm | €490.00 | Yearly (optional) | `tankly_farm_yearly` |

- [ ] Tax behavior: **Exclusive** (netto + USt) – standard for AT B2B
- [ ] Product tax code: **SaaS / electronically supplied services**
- [ ] Copy each `price_…` ID into env vars

### Stripe Tax

- [ ] Settings → Tax → add **Austria** registration (your UID)
- [ ] Add **EU OSS** registration when Steuerberater confirms
- [ ] Enable tax on subscriptions in Checkout

### Customer Portal

- [ ] Settings → Billing → Customer portal: enable
- [ ] Allow: update payment method, view invoices, cancel subscription
- [ ] Return URL: `https://your-domain/settings/billing`

### Webhooks

- [ ] Developers → Webhooks → Add endpoint: `https://your-domain/webhooks/stripe`
- [ ] Events to subscribe (minimum):
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_failed`
- [ ] Copy signing secret → `STRIPE_WEBHOOK_SECRET`

---

## 3. Environment variables

Add to `.env` / Northflank (never commit secrets):

```env
# Stripe (test keys during development)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Price IDs from Dashboard
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_YEARLY=price_...
STRIPE_PRICE_FARM_MONTHLY=price_...
STRIPE_PRICE_FARM_YEARLY=price_...

# Checkout redirect URLs (use BASE_URL in code)
# success: {BASE_URL}/settings/billing?success=1
# cancel:  {BASE_URL}/settings/billing?canceled=1
```

Update `app/config.py`:

```python
STRIPE_SECRET_KEY: str = ""
STRIPE_PUBLISHABLE_KEY: str = ""
STRIPE_WEBHOOK_SECRET: str = ""
STRIPE_PRICE_PRO_MONTHLY: str = ""
STRIPE_PRICE_FARM_MONTHLY: str = ""
# ...
```

Add to `requirements-prod.txt`:

```
stripe==11.6.0
```

---

## 4. Database schema

### Migration: `group_subscriptions`

```python
# alembic revision
class GroupSubscription(Base):
    __tablename__ = "group_subscriptions"

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    stripe_customer_id: Mapped[str | None]
    stripe_subscription_id: Mapped[str | None]
    status: Mapped[str]  # trialing|active|past_due|canceled|incomplete|unpaid
    tier: Mapped[str]    # free|pro|farm|partner (partner = platform grant, non-Stripe)
    current_period_end: Mapped[datetime | None]
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    trial_ends_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(onupdate=_utcnow)
```

### Migration: `billing_events` (idempotency)

```python
class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(unique=True, index=True)
    event_type: Mapped[str]
    processed_at: Mapped[datetime]
```

### Backfill

```sql
-- Every existing group starts on free tier
INSERT INTO group_subscriptions (group_id, status, tier)
SELECT id, 'active', 'free' FROM groups WHERE deleted_at IS NULL;
```

Keep `groups.subscription_tier` in sync via webhook handler (denormalized for fast reads).

---

## 5. Application architecture

```
┌─────────────┐     POST checkout      ┌──────────────────┐
│ Group admin │ ─────────────────────► │ Stripe Checkout  │
│ /settings/  │                        │ (hosted)         │
│   billing   │ ◄───────────────────── │                  │
└─────────────┘     redirect success   └────────┬─────────┘
                                                │ webhook
                                                ▼
                                       ┌──────────────────┐
                                       │ POST /webhooks/  │
                                       │      stripe      │
                                       └────────┬─────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │ group_subscriptions│
                                       │ groups.subscription│
                                       │      _tier        │
                                       └────────┬─────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │ entitlements.py   │
                                       │ (vehicle limits,  │
                                       │  feature flags)   │
                                       └──────────────────┘
```

### New files (Phase 23)

| File | Purpose |
|------|---------|
| `app/services/billing/stripe_client.py` | `stripe` SDK init, create checkout session, portal session |
| `app/services/billing/subscriptions.py` | DB sync from Stripe objects |
| `app/services/billing/webhooks.py` | Event dispatch + idempotency |
| `app/services/entitlements.py` | Tier limits (`max_vehicles`, feature flags) |
| `app/routes/billing.py` | Settings UI, checkout POST, portal redirect |
| `app/routes/webhooks_stripe.py` | Raw webhook endpoint |
| `app/templates/billing.html` | Current plan, upgrade buttons |
| `app/enums.py` | `SubscriptionTier`, `SubscriptionStatus` |

### CSRF exemption

In `app/csrf.py`, extend exempt paths:

```python
if request.url.path.startswith(("/cron/", "/webhooks/")):
    return
```

---

## 6. Implementation phases & checklist

### Phase 1 – Foundation (no charges yet)

- [ ] Add `stripe` to `requirements-prod.txt`
- [ ] Add Stripe settings to `app/config.py` and `.env.example`
- [ ] Create Alembic migration (`group_subscriptions`, `billing_events`)
- [ ] Add `SubscriptionTier` / `SubscriptionStatus` enums
- [ ] Implement `app/services/entitlements.py` with tier limits:

  | Tier | max_vehicles | analytics | export | maintenance |
  |------|-------------|-----------|--------|-------------|
  | free | 2 | no | no | no |
  | pro | 10 | yes | yes | yes |
  | farm | unlimited | yes | yes | yes |

- [ ] Default new groups to `tier=free` in `create_group()`
- [ ] Unit tests for `entitlements.py`

### Phase 2 – Stripe Checkout

- [ ] `stripe_client.create_checkout_session(group, price_id, user_email)`
  - `mode="subscription"`
  - `automatic_tax={"enabled": True}`
  - `tax_id_collection={"enabled": True}` for B2B VAT IDs
  - `metadata={"group_id": str(group.id), "user_id": str(user.id)}`
  - `customer_email` or reuse `stripe_customer_id`
- [ ] `POST /settings/billing/checkout` (admin only) → redirect to Stripe
- [ ] `GET /settings/billing` – show current tier, upgrade buttons
- [ ] Success/cancel flash messages on return

### Phase 3 – Webhooks

- [ ] `POST /webhooks/stripe` – verify signature with `STRIPE_WEBHOOK_SECRET`
- [ ] Idempotency: skip if `stripe_event_id` already in `billing_events`
- [ ] Handlers:
  - `checkout.session.completed` → link customer + subscription to group
  - `customer.subscription.updated` → sync status, tier, period end
  - `customer.subscription.deleted` → downgrade to `free`
  - `invoice.payment_failed` → set `past_due`, send email (optional)
- [ ] Update `groups.subscription_tier` in same transaction
- [ ] `log_event()` for `billing.upgrade`, `billing.cancel`, etc.

### Phase 4 – Customer Portal

- [ ] `POST /settings/billing/portal` → Stripe Billing Portal session
- [ ] Button: “Zahlungsmethode & Rechnungen verwalten”

### Phase 5 – Entitlement enforcement

- [ ] `require_entitlement("analytics")` dependency or inline checks
- [ ] Gate routes: `/analytics`, `/export/*`, `/maintenance/*`
- [ ] Gate `create_vehicle` when at vehicle limit → friendly upgrade message
- [ ] Dashboard banner when `past_due` or near vehicle limit
- [ ] Grace period: 7 days read-only on `past_due` (optional)

### Phase 6 – Polish

- [x] 14-day Pro trial (`trial_period_days=14` on Checkout)
- [x] Annual pricing toggle on billing page
- [x] Email on payment failure (reuse `fastapi-mail`)
- [x] Landing page pricing CTAs → `/register` with trial label when Stripe enabled
- [x] Remove footer note “Stripe folgt in Kürze” on landing page

---

## 7. Webhook handling

### Signature verification (required)

```python
import stripe
from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

def construct_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
```

### Mapping price → tier

```python
PRICE_TO_TIER = {
    settings.STRIPE_PRICE_PRO_MONTHLY: "pro",
    settings.STRIPE_PRICE_PRO_YEARLY: "pro",
    settings.STRIPE_PRICE_FARM_MONTHLY: "farm",
    settings.STRIPE_PRICE_FARM_YEARLY: "farm",
}
```

### Metadata contract

Always set on Checkout Session and Customer:

```json
{
  "group_id": "42",
  "initiated_by_user_id": "7"
}
```

Never trust client-supplied `group_id` from query params alone – verify admin role in DB before creating session.

### Edge cases

| Scenario | Action |
|----------|--------|
| Admin removed from group | Subscription stays on group; other admins manage billing |
| Group soft-deleted | Cancel Stripe subscription in delete handler |
| Duplicate webhook | `billing_events` unique constraint → 200 OK, no-op |
| User upgrades mid-cycle | Stripe prorates automatically |
| Payment fails | `past_due` → banner + email; after N days downgrade to free |

---

## 8. Entitlements & feature gating

### `app/services/entitlements.py` (sketch)

```python
TIER_LIMITS = {
    "free": {"max_vehicles": 2, "analytics": False, "export": False, "maintenance": False},
    "pro":  {"max_vehicles": 10, "analytics": True,  "export": True,  "maintenance": True},
    "farm": {"max_vehicles": None, "analytics": True, "export": True, "maintenance": True},
}

def get_group_tier(db, group_id: int) -> str:
    ...

def can_add_vehicle(db, group_id: int) -> bool:
    ...

def require_feature(tier: str, feature: str) -> None:
    ...
```

### Where to enforce

| Location | Check |
|----------|-------|
| `vehicles.py` create | `can_add_vehicle` |
| `analytics.py` | tier has `analytics` |
| `export.py` | tier has `export` |
| `maintenance.py` | tier has `maintenance` |

Return **403** with upgrade link for API-like routes; SSR forms show inline upgrade banner.

---

## 9. UI integration

### Billing settings page (`/settings/billing`)

Visible to **group admins only** (`require_role(Role.admin)`).

Sections:
1. Current plan badge (Free / Pro / Farm)
2. Status (Aktiv / Zahlung ausstehend / Gekündigt)
3. Renewal date (`current_period_end`)
4. Upgrade buttons → Checkout
5. “Abo verwalten” → Customer Portal
6. Invoice history link (portal)

Add nav link under Settings or on `group_settings.html`:

```html
<a href="/settings/billing">Abo &amp; Rechnungen</a>
```

### Landing page pricing CTAs (after billing live)

Change `href="/register"` on paid tiers to:
- Logged out → `/register`
- Logged in, no group → `/groups`
- Logged in, admin → `/settings/billing`

---

## 10. Testing

### Local webhook testing

```bash
# Install Stripe CLI
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed
```

### Test cases to add (`tests/test_billing.py`)

- [ ] Non-admin cannot access `/settings/billing`
- [ ] Checkout session created with correct `metadata.group_id`
- [ ] Webhook idempotency (same event twice → one DB update)
- [ ] `subscription.deleted` → tier reset to `free`
- [ ] Vehicle create blocked at free tier limit
- [ ] Analytics blocked on free tier
- [ ] Webhook with invalid signature → 400

### CI

- Mock `stripe` module in tests; no live API calls in GitHub Actions
- Use `stripe.Webhook.construct_event` with test secret in unit tests

---

## 11. Production go-live checklist

### Stripe

- [ ] Switch to **live** API keys (`sk_live_`, `pk_live_`)
- [ ] Live webhook endpoint registered with production URL
- [ ] Live products/prices created (or promote from test)
- [ ] Stripe Tax registrations active (AT + OSS)
- [ ] Customer portal configured for live mode

### App

- [ ] All env vars set on Northflank
- [ ] Legal pages complete (no placeholders)
- [ ] `BASE_URL` correct for Checkout redirects
- [ ] Entitlements enforced on all gated routes
- [ ] Audit log records billing events

### Smoke test (live)

- [ ] Register → create group → upgrade to Pro with real card (refund after)
- [ ] Verify invoice in Stripe Dashboard
- [ ] Open Customer Portal → cancel → verify downgrade at period end
- [ ] Verify tier limits (try 3rd vehicle on free after downgrade)

### Monitoring

- [ ] Sentry alert on webhook 500s
- [ ] Stripe Dashboard email alerts for failed payments
- [ ] Weekly check: `past_due` subscriptions

---

## 12. Bookkeeping (sevDesk / Billflow)

Stripe is the payment processor; **you** remain the seller (not MoR).

- [ ] Connect Stripe to **sevDesk** (MiracleSync or native integration) or **Billflow**
- [ ] Map Stripe payouts to bank account in Buchhaltung
- [ ] Stripe fees as Betriebsausgabe
- [ ] USt-Voranmeldung / OSS-Quartalsmeldung via Steuerberater
- [ ] Stripe Tax reports export for filings

---

## Quick reference: route map (after implementation)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | Public | Landing page |
| GET | `/settings/billing` | Admin + group | Billing overview |
| POST | `/settings/billing/checkout` | Admin | Start Stripe Checkout |
| POST | `/settings/billing/portal` | Admin | Stripe Customer Portal |
| POST | `/webhooks/stripe` | Stripe signature | Webhook handler |

---

## Related docs

- [PRODUCTION.md](./PRODUCTION.md) – deployment, env vars, health checks
- [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) – Phase 23 (complete)
- [STRIPE_GO_LIVE.md](./STRIPE_GO_LIVE.md) – production go-live checklist
- [PLATFORM_ADMIN.md](./PLATFORM_ADMIN.md) – operator dashboard (Phase 22, complete)
- [Stripe Docs: Checkout subscriptions](https://docs.stripe.com/billing/subscriptions/build-subscriptions?ui=checkout)
- [Stripe Tax EU](https://docs.stripe.com/tax)

---

*Last updated: 2026-06-20. Review with Steuerberater before first live charge.*
