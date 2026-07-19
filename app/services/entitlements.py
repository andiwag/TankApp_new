"""Subscription tier limits and feature gating."""

from sqlalchemy.orm import Session

from app.enums import SubscriptionTier
from app.models import GroupSubscription, Vehicle

TIER_LIMITS: dict[str, dict] = {
    SubscriptionTier.free.value: {
        "max_vehicles": 2,
        "analytics": False,
        "export": False,
        "maintenance": False,
    },
    SubscriptionTier.pro.value: {
        "max_vehicles": 10,
        "analytics": True,
        "export": True,
        "maintenance": True,
    },
    SubscriptionTier.farm.value: {
        "max_vehicles": None,
        "analytics": True,
        "export": True,
        "maintenance": True,
    },
    # Non-Stripe complimentary tier (platform grant only); same limits as farm.
    SubscriptionTier.partner.value: {
        "max_vehicles": None,
        "analytics": True,
        "export": True,
        "maintenance": True,
    },
}


def vehicle_limit_for_tier(tier: str) -> int | None:
    return TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.free.value])[
        "max_vehicles"
    ]


def tier_has_feature(tier: str, feature: str) -> bool:
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.free.value])
    return bool(limits.get(feature, False))


def _subscription_for_group(db: Session, group_id: int) -> GroupSubscription | None:
    return (
        db.query(GroupSubscription)
        .filter(GroupSubscription.group_id == group_id)
        .first()
    )


def get_group_tier(db: Session, group_id: int) -> str:
    sub = _subscription_for_group(db, group_id)
    if sub is None:
        return SubscriptionTier.free.value
    return sub.tier


def effective_tier(db: Session, group_id: int) -> str:
    sub = _subscription_for_group(db, group_id)
    if sub is None:
        return SubscriptionTier.free.value
    if sub.status in ("canceled", "unpaid", "incomplete_expired"):
        return SubscriptionTier.free.value
    return sub.tier


def active_vehicle_count(db: Session, group_id: int) -> int:
    return (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .count()
    )


def can_add_vehicle(db: Session, group_id: int) -> bool:
    tier = effective_tier(db, group_id)
    limit = vehicle_limit_for_tier(tier)
    if limit is None:
        return True
    return active_vehicle_count(db, group_id) < limit
