"""Shared billing constants."""

# Stripe subscription statuses that still grant paid entitlements.
ACTIVE_PAID_STATUSES: frozenset[str] = frozenset({"active", "trialing", "past_due"})
