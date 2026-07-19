"""Billing settings, Checkout, and Customer Portal."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_active_group, require_role
from app.enums import Role, SubscriptionTier
from app.flash import set_flash
from app.models import Group, User
from app.services.billing import price_catalog, stripe_client
from app.services.billing.subscriptions import (
    ensure_group_subscription,
    has_active_paid_subscription,
    reconcile_group_subscription,
)
from app.services.entitlements import (
    TIER_LIMITS,
    effective_tier,
    vehicle_limit_for_tier,
)
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _tier_label(tier: str) -> str:
    labels = {
        SubscriptionTier.free.value: "Free",
        SubscriptionTier.pro.value: "Pro",
        SubscriptionTier.farm.value: "Farm",
        SubscriptionTier.partner.value: "Partner",
    }
    return labels.get(tier, tier)


def _status_label(status: str) -> str:
    labels = {
        "active": "Aktiv",
        "trialing": "Testphase",
        "past_due": "Zahlung ausstehend",
        "canceled": "Gekündigt",
        "unpaid": "Unbezahlt",
    }
    return labels.get(status, status)


def _checkout_plans(catalog: dict, *, interval: str = "month") -> list[dict]:
    labels = {
        settings.STRIPE_LOOKUP_PRO_MONTHLY: "Upgrade auf Pro (monatlich)",
        settings.STRIPE_LOOKUP_FARM_MONTHLY: "Upgrade auf Farm (monatlich)",
        settings.STRIPE_LOOKUP_PRO_YEARLY: "Upgrade auf Pro (jährlich)",
        settings.STRIPE_LOOKUP_FARM_YEARLY: "Upgrade auf Farm (jährlich)",
    }
    plans = []
    for lookup_key, entry in catalog.items():
        if entry.interval != interval:
            continue
        label = labels.get(lookup_key)
        if not label:
            continue
        plans.append(
            {
                "lookup_key": lookup_key,
                "label": label,
                "tier": entry.tier,
                "interval": entry.interval,
            }
        )
    return plans


def _billing_interval(raw: str | None) -> str:
    return "year" if raw == "year" else "month"


def _billing_context(db: Session, group: Group, *, interval: str = "month") -> dict:
    sub = ensure_group_subscription(db, group.id)
    tier = effective_tier(db, group.id)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.free.value])
    vehicle_limit = vehicle_limit_for_tier(tier)
    catalog = price_catalog.get_catalog() if settings.stripe_enabled else {}
    has_yearly = any(entry.interval == "year" for entry in catalog.values())
    return {
        "subscription": sub,
        "effective_tier": tier,
        "tier_label": _tier_label(tier),
        "status_label": _status_label(sub.status),
        "vehicle_limit": vehicle_limit,
        "features": limits,
        "has_active_subscription": has_active_paid_subscription(sub),
        "is_partner_tier": tier == SubscriptionTier.partner.value,
        "stripe_enabled": settings.stripe_enabled,
        "stripe_catalog_ready": bool(catalog),
        "checkout_plans": _checkout_plans(catalog, interval=interval),
        "billing_interval": interval,
        "has_yearly_plans": has_yearly,
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "trial_days": settings.STRIPE_TRIAL_DAYS,
    }


def _maybe_reconcile_from_stripe(db: Session, group_id: int) -> None:
    sub = ensure_group_subscription(db, group_id)
    if not settings.stripe_enabled or not sub.stripe_subscription_id:
        return
    try:
        reconcile_group_subscription(db, group_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Stripe reconcile failed for group %s", group_id)


@router.get("/settings/billing")
async def billing_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _admin: User = Depends(require_role(Role.admin.value)),
):
    if request.query_params.get("success") or request.query_params.get("refresh"):
        _maybe_reconcile_from_stripe(db, group.id)
    interval = _billing_interval(request.query_params.get("interval"))
    ctx = _billing_context(db, group, interval=interval)
    success = request.query_params.get("success")
    canceled = request.query_params.get("canceled")
    if success:
        ctx["flash_success"] = "Abo erfolgreich aktualisiert."
    if canceled:
        ctx["flash_info"] = "Checkout abgebrochen."
    if settings.stripe_enabled and not ctx["stripe_catalog_ready"]:
        ctx["flash_info"] = (
            "Stripe-Tarife konnten nicht geladen werden. Prüfe Lookup Keys "
            "und metadata.tier auf den Prices in Stripe."
        )
    return templates.TemplateResponse(request, "billing.html", ctx)


@router.post("/settings/billing/checkout")
async def billing_checkout_post(
    lookup_key: str = Form(...),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user: User = Depends(require_role(Role.admin.value)),
):
    if not settings.stripe_enabled:
        raise HTTPException(status_code=503, detail="Billing not configured")

    catalog_price = price_catalog.resolve_checkout_price(lookup_key)
    if catalog_price is None:
        raise HTTPException(status_code=400, detail="Invalid price")

    sub = ensure_group_subscription(db, group.id)
    if sub.tier == SubscriptionTier.partner.value:
        response = RedirectResponse(url="/settings/billing", status_code=303)
        set_flash(
            response,
            "Partner-Tarif ist kein Stripe-Abo. Bitte Tankly, den Partner-Tarif "
            "zu entziehen, bevor du ein kostenpflichtiges Abo startest.",
            "info",
        )
        return response
    if has_active_paid_subscription(sub):
        response = RedirectResponse(url="/settings/billing", status_code=303)
        set_flash(
            response,
            "Du hast bereits ein aktives Abo. Verwalte Tarifwechsel und Kündigung "
            "über das Kundenportal.",
            "info",
        )
        return response

    session = stripe_client.create_checkout_session(
        group=group,
        user=user,
        price_id=catalog_price.price_id,
        customer_id=sub.stripe_customer_id,
        trial_days=(
            settings.STRIPE_TRIAL_DAYS
            if catalog_price.tier == SubscriptionTier.pro.value
            and settings.STRIPE_TRIAL_DAYS > 0
            else None
        ),
    )
    return RedirectResponse(url=session.url, status_code=303)


@router.post("/settings/billing/portal")
async def billing_portal_post(
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _admin: User = Depends(require_role(Role.admin.value)),
):
    if not settings.stripe_enabled:
        raise HTTPException(status_code=503, detail="Billing not configured")

    sub = ensure_group_subscription(db, group.id)
    if not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer")

    session = stripe_client.create_portal_session(customer_id=sub.stripe_customer_id)
    return RedirectResponse(url=session.url, status_code=303)
