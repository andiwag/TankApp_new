"""Stripe SDK helpers for Checkout and Customer Portal."""

from __future__ import annotations

from typing import TYPE_CHECKING

import stripe

from app.config import settings

if TYPE_CHECKING:
    from app.models import Group, User


def _configure_stripe() -> None:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(
    *,
    group: Group,
    user: User,
    price_id: str,
    customer_id: str | None = None,
    trial_days: int | None = None,
) -> stripe.checkout.Session:
    _configure_stripe()
    base_url = settings.BASE_URL or "http://localhost:8000"
    subscription_data: dict = {
        "metadata": {
            "group_id": str(group.id),
        },
    }
    if trial_days and trial_days > 0:
        subscription_data["trial_period_days"] = trial_days
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base_url}/settings/billing?success=1",
        "cancel_url": f"{base_url}/settings/billing?canceled=1",
        "automatic_tax": {"enabled": True},
        "tax_id_collection": {"enabled": True},
        "metadata": {
            "group_id": str(group.id),
            "initiated_by_user_id": str(user.id),
        },
        "subscription_data": subscription_data,
    }
    if customer_id:
        params["customer"] = customer_id
    else:
        params["customer_email"] = user.email
    return stripe.checkout.Session.create(**params)


def create_portal_session(*, customer_id: str) -> stripe.billing_portal.Session:
    _configure_stripe()
    base_url = settings.BASE_URL or "http://localhost:8000"
    return stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{base_url}/settings/billing",
    )


def cancel_subscription(subscription_id: str) -> stripe.Subscription:
    _configure_stripe()
    return stripe.Subscription.cancel(subscription_id)


def retrieve_subscription(subscription_id: str) -> stripe.Subscription:
    _configure_stripe()
    return stripe.Subscription.retrieve(
        subscription_id,
        expand=["items.data.price", "items.data.price.product"],
    )
