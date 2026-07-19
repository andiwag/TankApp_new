# Tankly — Phase kickoff prompt

Use when starting a **new development-plan phase**. All TDD workflow, architecture, testing, git, and reporting rules live in [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) — do not duplicate them here.

---

## Current plan status

Authoritative task lists and acceptance criteria: `.docs/DEVELOPMENT_PLAN.md`.

| Phases | Status |
|--------|--------|
| **0–16** | Original MVP — complete |
| **17–21** | Post-MVP (maintenance, analytics/export/cost, audit UI, sessions & production hardening, marketing/beta gate) — complete |
| **22** | Platform admin (`/platform`) — **complete** |
| **23** | Stripe billing + launch polish — **complete** |

**Next work:** Production go-live per [STRIPE_GO_LIVE.md](../.docs/STRIPE_GO_LIVE.md) unless the user directs otherwise.

---

## Before starting the phase

1. `.docs/DEVELOPMENT_PLAN.md` — unchecked tasks, planned tests, acceptance criteria for this phase.
2. Feature spec when one exists — e.g. `.docs/PLATFORM_ADMIN.md` (22), `.docs/STRIPE_BILLING.md` (23).
3. `.docs/DECISION_LOG.md` — skim related `D-XXX` entries; do not contradict them.
4. `.docs/BETA_DEPLOY.md` / `.docs/PRODUCTION.md` — only if the phase touches deploy or env vars.

General architecture and routes: `.docs/TECHNICAL_DOCUMENTATION.md` (see also copilot-instructions §1).

---

## Phase loop

Follow [copilot-instructions §2–3](../.github/copilot-instructions.md#2-non-negotiable-test-driven-development), then:

1. **Announce** the phase and what it covers.
2. **Write every test listed** in the development plan for this phase before implementation.
3. **Verify** all acceptance criteria when implementation is green.
4. **Update docs** — check off tasks in `.docs/DEVELOPMENT_PLAN.md`; append new `D-XXX` entries to `.docs/DECISION_LOG.md`.
5. **Stop** when the phase is complete; confirm with the user before starting the next phase.

---

## Start now

Phases **0–23** are complete in `.docs/DEVELOPMENT_PLAN.md`. Do **not** start a new development-plan phase unless the user asks.

Default next work: production go-live checklist in [STRIPE_GO_LIVE.md](../.docs/STRIPE_GO_LIVE.md), or follow the user’s explicit direction.
