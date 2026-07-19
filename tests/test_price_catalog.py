"""Tests for Stripe price catalog (lookup keys + tier metadata)."""

from types import SimpleNamespace

import pytest
from app.config import settings
from app.enums import SubscriptionTier
from app.services.billing import price_catalog


@pytest.fixture(autouse=True)
def clear_catalog_cache():
    price_catalog.clear_catalog_cache()
    yield
    price_catalog.clear_catalog_cache()


class TestTierFromStripePrice:
    def test_reads_tier_from_price_metadata(self):
        price = SimpleNamespace(metadata={"tier": "pro"})
        assert price_catalog.tier_from_stripe_price(price) == SubscriptionTier.pro.value

    def test_reads_tier_from_product_metadata_when_price_missing(self):
        product = SimpleNamespace(metadata={"tier": "farm"})
        price = SimpleNamespace(metadata={}, product=product)
        assert (
            price_catalog.tier_from_stripe_price(price) == SubscriptionTier.farm.value
        )

    def test_rejects_unknown_tier_metadata(self):
        price = SimpleNamespace(metadata={"tier": "enterprise"})
        assert price_catalog.tier_from_stripe_price(price) is None

    def test_rejects_partner_tier_metadata(self):
        """partner is platform-only; Stripe prices must not map to it."""
        price = SimpleNamespace(metadata={"tier": "partner"})
        assert price_catalog.tier_from_stripe_price(price) is None


class TestCatalogResolution:
    def test_get_catalog_resolves_lookup_keys_from_stripe(self, monkeypatch):
        def fake_list(*, lookup_keys, active, limit):
            key = lookup_keys[0]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        id=f"price_{key}",
                        lookup_key=key,
                        metadata={"tier": "pro" if "pro" in key else "farm"},
                        recurring=SimpleNamespace(interval="month"),
                        product=SimpleNamespace(metadata={}),
                    )
                ]
            )

        monkeypatch.setattr(
            "app.services.billing.price_catalog.stripe.Price.list",
            fake_list,
        )
        monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")

        catalog = price_catalog.get_catalog()
        assert "tankly_pro_monthly" in catalog
        assert catalog["tankly_pro_monthly"].price_id == "price_tankly_pro_monthly"
        assert catalog["tankly_pro_monthly"].tier == SubscriptionTier.pro.value

    def test_resolve_checkout_price_rejects_unknown_lookup_key(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.billing.price_catalog.get_catalog",
            lambda: {},
        )
        assert price_catalog.resolve_checkout_price("unknown_key") is None
