"""Stripe webhook dispatch with idempotency."""

from __future__ import annotations

import logging

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BillingEvent
from app.services.billing import stripe_client
from app.services.billing import subscriptions as subscription_service
from app.services.billing.subscriptions import parse_stripe_group_id

logger = logging.getLogger(__name__)


def construct_event(payload: bytes, sig_header: str):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.STRIPE_WEBHOOK_SECRET,
    )


def _initiated_by_user_id(event) -> int | None:
    obj = event.data.object
    metadata = getattr(obj, "metadata", None) or {}
    raw = metadata.get("initiated_by_user_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def _subscription_from_event_object(obj):
    subscription_id = getattr(obj, "id", None)
    if subscription_id and getattr(obj, "object", "") == "subscription":
        return stripe_client.retrieve_subscription(str(subscription_id))
    nested_id = getattr(obj, "subscription", None)
    if nested_id:
        return stripe_client.retrieve_subscription(str(nested_id))
    return obj


def dispatch_event(db: Session, event) -> int | None:
    event_type = event.type
    obj = event.data.object
    user_id = _initiated_by_user_id(event)
    notify_group_id: int | None = None

    if event_type == "checkout.session.completed":
        subscription_service.sync_checkout_session_completed(db, obj, user_id=user_id)
        subscription_id = getattr(obj, "subscription", None)
        if subscription_id:
            stripe_sub = stripe_client.retrieve_subscription(str(subscription_id))
            subscription_service.sync_subscription_from_stripe(
                db, stripe_sub, user_id=user_id
            )
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        deleted = event_type == "customer.subscription.deleted"
        stripe_sub = _subscription_from_event_object(obj)
        subscription_service.sync_subscription_from_stripe(
            db,
            stripe_sub,
            event_type="deleted" if deleted else None,
            user_id=user_id,
        )
    elif event_type == "invoice.payment_failed":
        stripe_sub = _subscription_from_event_object(obj)
        subscription_service.sync_subscription_from_stripe(db, stripe_sub)
        group_id = parse_stripe_group_id(getattr(stripe_sub, "metadata", None))
        if group_id is None:
            group_id = parse_stripe_group_id(getattr(obj, "metadata", None))
        if group_id is not None:
            notify_group_id = group_id

    return notify_group_id


def process_stripe_webhook(db: Session, payload: bytes, sig_header: str) -> int | None:
    try:
        event = construct_event(payload, sig_header)
    except stripe.error.SignatureVerificationError as exc:
        raise ValueError("Invalid signature") from exc

    db.add(
        BillingEvent(
            stripe_event_id=event.id,
            event_type=event.type,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return

    try:
        notify_group_id = dispatch_event(db, event)
        db.commit()
        return notify_group_id
    except Exception:
        db.rollback()
        logger.exception("Stripe webhook processing failed for event %s", event.id)
        raise
