"""Platform-only complimentary partner tier grants (non-Stripe)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.audit import log_event
from app.enums import SubscriptionTier
from app.models import Group, GroupSubscription
from app.services.billing.subscriptions import (
    ensure_group_subscription,
    sync_group_tier_column,
)
from app.time_utils import utc_now


class PartnerGrantError(Exception):
    """Raised when a partner grant/revoke cannot proceed."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _active_group(db: Session, group_id: int) -> Group | None:
    return (
        db.query(Group)
        .filter(
            Group.id == group_id,
            Group.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def grant_partner_tier(
    db: Session, group_id: int, *, actor_user_id: int
) -> GroupSubscription:
    if _active_group(db, group_id) is None:
        raise PartnerGrantError("Betrieb nicht gefunden oder gelöscht.")

    sub = ensure_group_subscription(db, group_id)
    if sub.stripe_subscription_id:
        raise PartnerGrantError(
            "Partner-Tarif kann nicht vergeben werden: Es existiert bereits ein "
            "Stripe-Abo. Bitte zuerst im Stripe-Kundenportal kündigen."
        )

    if sub.tier == SubscriptionTier.partner.value:
        return sub

    sub.tier = SubscriptionTier.partner.value
    sub.status = "active"
    sub.cancel_at_period_end = False
    sub.current_period_end = None
    sub.trial_ends_at = None
    sub.updated_at = utc_now()
    sync_group_tier_column(db, group_id, SubscriptionTier.partner.value)
    log_event(
        db,
        group_id=group_id,
        user_id=actor_user_id,
        action="platform.billing.grant_partner",
        entity_type="group",
        entity_id=group_id,
    )
    db.flush()
    return sub


def revoke_partner_tier(
    db: Session, group_id: int, *, actor_user_id: int
) -> GroupSubscription:
    if _active_group(db, group_id) is None:
        raise PartnerGrantError("Betrieb nicht gefunden oder gelöscht.")

    sub = ensure_group_subscription(db, group_id)
    if sub.tier != SubscriptionTier.partner.value:
        raise PartnerGrantError("Dieser Betrieb hat keinen Partner-Tarif.")
    if sub.stripe_subscription_id:
        raise PartnerGrantError(
            "Partner-Tarif kann nicht entzogen werden: Stripe-Abo vorhanden."
        )

    sub.tier = SubscriptionTier.free.value
    sub.status = "active"
    sub.cancel_at_period_end = False
    sub.current_period_end = None
    sub.trial_ends_at = None
    sub.updated_at = utc_now()
    sync_group_tier_column(db, group_id, SubscriptionTier.free.value)
    log_event(
        db,
        group_id=group_id,
        user_id=actor_user_id,
        action="platform.billing.revoke_partner",
        entity_type="group",
        entity_id=group_id,
    )
    db.flush()
    return sub
