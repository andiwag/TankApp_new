"""Resolve Stripe prices by lookup key; tier comes from Stripe metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import stripe

from app.config import settings
from app.enums import SubscriptionTier

if TYPE_CHECKING:
    pass

_VALID_TIERS = frozenset(
    t.value for t in SubscriptionTier if t != SubscriptionTier.free
)

_catalog_cache: dict[str, CatalogPrice] | None = None


@dataclass(frozen=True)
class CatalogPrice:
    lookup_key: str
    price_id: str
    tier: str
    interval: str | None


def clear_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None


def configured_lookup_keys() -> list[str]:
    return [
        key
        for key in (
            settings.STRIPE_LOOKUP_PRO_MONTHLY,
            settings.STRIPE_LOOKUP_PRO_YEARLY,
            settings.STRIPE_LOOKUP_FARM_MONTHLY,
            settings.STRIPE_LOOKUP_FARM_YEARLY,
        )
        if key
    ]


def tier_from_stripe_price(price) -> str | None:
    metadata = getattr(price, "metadata", None) or {}
    tier = metadata.get("tier")
    if isinstance(tier, str) and tier in _VALID_TIERS:
        return tier

    product = getattr(price, "product", None)
    if product is not None and not isinstance(product, str):
        product_metadata = getattr(product, "metadata", None) or {}
        tier = product_metadata.get("tier")
        if isinstance(tier, str) and tier in _VALID_TIERS:
            return tier
    return None


def _fetch_price_by_lookup_key(lookup_key: str) -> CatalogPrice | None:
    stripe.api_key = settings.STRIPE_SECRET_KEY
    result = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
    if not result.data:
        return None
    price = result.data[0]
    tier = tier_from_stripe_price(price)
    if tier is None:
        return None
    recurring = getattr(price, "recurring", None)
    interval = getattr(recurring, "interval", None) if recurring else None
    return CatalogPrice(
        lookup_key=lookup_key,
        price_id=price.id,
        tier=tier,
        interval=interval,
    )


def get_catalog() -> dict[str, CatalogPrice]:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    catalog: dict[str, CatalogPrice] = {}
    if settings.stripe_enabled:
        for lookup_key in configured_lookup_keys():
            entry = _fetch_price_by_lookup_key(lookup_key)
            if entry:
                catalog[lookup_key] = entry
    _catalog_cache = catalog
    return catalog


def resolve_checkout_price(lookup_key: str) -> CatalogPrice | None:
    return get_catalog().get(lookup_key)


def tier_from_price_id(price_id: str) -> str | None:
    for entry in get_catalog().values():
        if entry.price_id == price_id:
            return entry.tier
    return None
