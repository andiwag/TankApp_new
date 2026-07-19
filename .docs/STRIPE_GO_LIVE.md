# Stripe go-live checklist

Use this after Phase 23 billing code is deployed. Full spec: [STRIPE_BILLING.md](./STRIPE_BILLING.md).

## 1. Business & legal (Austria)

- [ ] Steuerberater: Kleinunternehmer vs USt, UID, EU OSS if needed
- [ ] Set all `COMPANY_*` env vars (see `.env.example`)
- [ ] Legal review of `/impressum`, `/datenschutz`, `/agb`
- [ ] AVV with hosting, Stripe, mail provider

## 2. Stripe Dashboard (test mode first)

- [ ] Products: Pro (€19/mo, €190/yr), Farm (€49/mo, €490/yr)
- [ ] Lookup keys: `tankly_pro_monthly`, `tankly_pro_yearly`, `tankly_farm_monthly`, `tankly_farm_yearly`
- [ ] Each Price: `metadata.tier` = `pro` or `farm`
- [ ] Stripe Tax: Austria (+ OSS when confirmed)
- [ ] Customer portal enabled; return URL `{BASE_URL}/settings/billing`
- [ ] Webhook: `{BASE_URL}/webhooks/stripe` with events:
  - `checkout.session.completed`
  - `customer.subscription.*`
  - `invoice.paid`, `invoice.payment_failed`

## 3. App environment

```env
ENV=production
BASE_URL=https://www.tankly.at
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_TRIAL_DAYS=14
COMPANY_LEGAL_NAME=...
COMPANY_STREET=...
COMPANY_CITY=...
COMPANY_EMAIL=...
MAIL_USERNAME=...
MAIL_PASSWORD=...
```

- [ ] Run `alembic upgrade head` on production DB
- [ ] `RUN_MIGRATIONS_ON_START=true` or migrate job before deploy

## 4. Local / staging test (Stripe test keys)

```bash
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe
```

- [ ] Register → create group → `/settings/billing` → upgrade Pro (trial)
- [ ] Webhook updates tier; dashboard shows Pro features
- [ ] Customer portal: update card, cancel
- [ ] `stripe trigger invoice.payment_failed` → admin email (if mail configured)

## 5. Production smoke test

- [ ] One real Pro subscription → verify invoice → refund/cancel
- [ ] Downgrade: vehicle limit enforced on free tier
- [ ] Sentry/monitoring for webhook 500s

## 6. Launch

- [ ] Remove or keep `REGISTRATION_INVITE_CODE` (public vs private beta)
- [ ] Landing page shows trial note when Stripe + `BASE_URL` configured
- [ ] Monitor `past_due` subscriptions weekly
