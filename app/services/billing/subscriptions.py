"""Persist Stripe subscription state on groups."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.audit import log_event
from app.enums import SubscriptionTier
from app.models import Group, GroupSubscription
from app.services.billing import price_catalog
from app.services.billing.constants import ACTIVE_PAID_STATUSES
from app.time_utils import UTC

logger = logging.getLogger(__name__)


def parse_stripe_group_id(metadata) -> int | None:
    return _parse_group_id(metadata)


def _parse_group_id(metadata) -> int | None:
    raw = (metadata or {}).get("group_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring Stripe metadata with invalid group_id: %r", raw)
        return None


def _active_group(db: Session, group_id: int) -> Group | None:
    return (
        db.query(Group)
        .filter(
            Group.id == group_id,
            Group.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def has_active_paid_subscription(sub: GroupSubscription) -> bool:
    return bool(
        sub.stripe_subscription_id
        and sub.status in ACTIVE_PAID_STATUSES
        and sub.tier != SubscriptionTier.free.value
    )


def _utc_from_timestamp(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def sync_group_tier_column(db: Session, group_id: int, tier: str) -> None:
    group = db.query(Group).filter(Group.id == group_id).first()
    if group:
        group.subscription_tier = tier


def ensure_group_subscription(db: Session, group_id: int) -> GroupSubscription:
    sub = (
        db.query(GroupSubscription)
        .filter(GroupSubscription.group_id == group_id)
        .first()
    )
    if sub:
        return sub

    sub = GroupSubscription(
        group_id=group_id,
        status="active",
        tier=SubscriptionTier.free.value,
    )
    db.add(sub)
    db.flush()
    sync_group_tier_column(db, group_id, SubscriptionTier.free.value)
    return sub


def _tier_from_stripe_subscription(stripe_sub) -> str:
    items = getattr(getattr(stripe_sub, "items", None), "data", None) or []
    for item in items:
        price = getattr(item, "price", None)
        if price is None:
            continue
        tier = price_catalog.tier_from_stripe_price(price)
        if tier:
            return tier
        price_id = getattr(price, "id", None)
        if price_id:
            catalog_tier = price_catalog.tier_from_price_id(price_id)
            if catalog_tier:
                return catalog_tier
    return SubscriptionTier.free.value


def sync_subscription_from_stripe(
    db: Session,
    stripe_sub,
    *,
    event_type: str | None = None,
    user_id: int | None = None,
) -> GroupSubscription | None:
    group_id = _parse_group_id(getattr(stripe_sub, "metadata", None))
    if group_id is None:
        return None
    if _active_group(db, group_id) is None:
        logger.info("Skipping Stripe sync for missing or deleted group_id=%s", group_id)
        return None

    sub = ensure_group_subscription(db, group_id)

    status = getattr(stripe_sub, "status", sub.status)
    if event_type == "deleted" or status in ("canceled", "unpaid", "incomplete_expired"):
        sub.tier = SubscriptionTier.free.value
        sub.status = status if status else "canceled"
        sub.stripe_subscription_id = None
        sub.current_period_end = None
        sub.cancel_at_period_end = False
        sub.trial_ends_at = None
        sync_group_tier_column(db, group_id, SubscriptionTier.free.value)
        db.flush()
        if user_id:
            log_event(db, group_id, user_id, "billing.cancel", "group", group_id)
        return sub

    sub.stripe_subscription_id = getattr(stripe_sub, "id", sub.stripe_subscription_id)
    customer = getattr(stripe_sub, "customer", None)
    if customer:
        sub.stripe_customer_id = str(customer)
    sub.status = status
    sub.tier = _tier_from_stripe_subscription(stripe_sub)
    sub.current_period_end = _utc_from_timestamp(
        getattr(stripe_sub, "current_period_end", None)
    )
    sub.cancel_at_period_end = bool(
        getattr(stripe_sub, "cancel_at_period_end", False)
    )
    sub.trial_ends_at = _utc_from_timestamp(getattr(stripe_sub, "trial_end", None))
    sync_group_tier_column(db, group_id, sub.tier)
    db.flush()
    return sub


def sync_checkout_session_completed(db: Session, session, user_id: int | None = None):
    group_id = _parse_group_id(getattr(session, "metadata", None))
    if group_id is None:
        return None
    if _active_group(db, group_id) is None:
        logger.info(
            "Skipping checkout sync for missing or deleted group_id=%s", group_id
        )
        return None

    sub = ensure_group_subscription(db, group_id)
    customer = getattr(session, "customer", None)
    if customer:
        sub.stripe_customer_id = str(customer)
    subscription_id = getattr(session, "subscription", None)
    if subscription_id:
        sub.stripe_subscription_id = str(subscription_id)
    if user_id:
        log_event(db, group_id, user_id, "billing.upgrade", "group", group_id)
    return sub


def reconcile_group_subscription(
    db: Session, group_id: int
) -> GroupSubscription | None:
    """Re-fetch subscription state from Stripe and mirror locally."""
    if _active_group(db, group_id) is None:
        return None

    sub = ensure_group_subscription(db, group_id)
    if not sub.stripe_subscription_id:
        return sub

    from app.services.billing import stripe_client

    stripe_sub = stripe_client.retrieve_subscription(sub.stripe_subscription_id)
    return sync_subscription_from_stripe(db, stripe_sub)


def reconcile_all_stripe_subscriptions(db: Session) -> int:
    """Reconcile every group that has a Stripe subscription id."""
    rows = (
        db.query(GroupSubscription)
        .filter(GroupSubscription.stripe_subscription_id.isnot(None))
        .all()
    )
    count = 0
    for sub in rows:
        if reconcile_group_subscription(db, sub.group_id):
            count += 1
    return count
