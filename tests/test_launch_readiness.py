"""Launch readiness: legal pages, billing polish, marketing CTAs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.config import settings
from app.enums import Role, SubscriptionTier
from app.services.billing.price_catalog import CatalogPrice, clear_catalog_cache

from tests.test_billing import _ensure_subscription


@pytest.fixture
def stripe_settings(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_billing")
    monkeypatch.setattr(settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_billing")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setattr(settings, "BASE_URL", "http://test")


@pytest.fixture
def stripe_catalog(monkeypatch):
    clear_catalog_cache()
    catalog = {
        settings.STRIPE_LOOKUP_PRO_MONTHLY: CatalogPrice(
            settings.STRIPE_LOOKUP_PRO_MONTHLY,
            "price_pro_monthly",
            SubscriptionTier.pro.value,
            "month",
        ),
        settings.STRIPE_LOOKUP_PRO_YEARLY: CatalogPrice(
            settings.STRIPE_LOOKUP_PRO_YEARLY,
            "price_pro_yearly",
            SubscriptionTier.pro.value,
            "year",
        ),
        settings.STRIPE_LOOKUP_FARM_MONTHLY: CatalogPrice(
            settings.STRIPE_LOOKUP_FARM_MONTHLY,
            "price_farm_monthly",
            SubscriptionTier.farm.value,
            "month",
        ),
        settings.STRIPE_LOOKUP_FARM_YEARLY: CatalogPrice(
            settings.STRIPE_LOOKUP_FARM_YEARLY,
            "price_farm_yearly",
            SubscriptionTier.farm.value,
            "year",
        ),
    }
    monkeypatch.setattr(
        "app.services.billing.price_catalog.get_catalog",
        lambda: catalog,
    )
    yield catalog
    clear_catalog_cache()


class TestLegalPages:
    async def test_impressum_shows_company_when_configured(self, client, monkeypatch):
        monkeypatch.setattr(settings, "COMPANY_LEGAL_NAME", "Tankly GmbH")
        monkeypatch.setattr(settings, "COMPANY_STREET", "Musterstraße 1")
        monkeypatch.setattr(settings, "COMPANY_CITY", "1010 Wien")
        monkeypatch.setattr(settings, "COMPANY_EMAIL", "info@tankly.at")

        response = await client.get("/impressum")
        assert response.status_code == 200
        assert "Tankly GmbH" in response.text
        assert "Musterstraße 1" in response.text
        assert "Platzhalter" not in response.text

    async def test_impressum_warns_when_company_not_configured(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(settings, "COMPANY_LEGAL_NAME", "")
        monkeypatch.setattr(settings, "COMPANY_STREET", "")
        monkeypatch.setattr(settings, "COMPANY_CITY", "")
        monkeypatch.setattr(settings, "COMPANY_EMAIL", "")

        response = await client.get("/impressum")
        assert response.status_code == 200
        assert "COMPANY_*" in response.text


class TestLandingBillingPolish:
    async def test_landing_has_no_stripe_coming_soon_note(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert "folgt in Kürze" not in response.text

    async def test_landing_pro_cta_mentions_trial_when_stripe_enabled(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
        monkeypatch.setattr(settings, "STRIPE_TRIAL_DAYS", 14)

        response = await client.get("/")
        assert "14 Tage Pro testen" in response.text


class TestBillingPolish:
    async def test_checkout_includes_pro_trial_days(
        self,
        client,
        auth_group,
        db,
        stripe_settings,
        stripe_catalog,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "STRIPE_TRIAL_DAYS", 14)
        _, group = auth_group(role=Role.admin.value)
        _ensure_subscription(db, group.id)

        mock_session = SimpleNamespace(url="https://checkout.stripe.com/test")
        with patch(
            "app.services.billing.stripe_client.create_checkout_session",
            return_value=mock_session,
        ) as create_checkout:
            response = await client.post(
                "/settings/billing/checkout",
                data={"lookup_key": settings.STRIPE_LOOKUP_PRO_MONTHLY},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert create_checkout.call_args.kwargs["trial_days"] == 14

    async def test_checkout_skips_trial_for_farm(
        self,
        client,
        auth_group,
        db,
        stripe_settings,
        stripe_catalog,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "STRIPE_TRIAL_DAYS", 14)
        _, group = auth_group(role=Role.admin.value)
        _ensure_subscription(db, group.id)

        mock_session = SimpleNamespace(url="https://checkout.stripe.com/test")
        with patch(
            "app.services.billing.stripe_client.create_checkout_session",
            return_value=mock_session,
        ) as create_checkout:
            response = await client.post(
                "/settings/billing/checkout",
                data={"lookup_key": settings.STRIPE_LOOKUP_FARM_MONTHLY},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert create_checkout.call_args.kwargs["trial_days"] is None

    async def test_billing_page_filters_yearly_plans(
        self,
        client,
        auth_group,
        db,
        stripe_settings,
        stripe_catalog,
    ):
        _, group = auth_group(role=Role.admin.value)
        _ensure_subscription(db, group.id)

        response = await client.get("/settings/billing?interval=year")
        assert response.status_code == 200
        assert "Upgrade auf Pro (jährlich)" in response.text
        assert "Upgrade auf Pro (monatlich)" not in response.text


class TestPaymentFailedEmail:
    async def test_payment_failed_webhook_notifies_admins(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        monkeypatch,
    ):
        from app.models import BillingEvent

        monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test")
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
        monkeypatch.setattr(settings, "MAIL_USERNAME", "user")
        monkeypatch.setattr(settings, "MAIL_PASSWORD", "pass")
        monkeypatch.setattr(settings, "BASE_URL", "https://app.tankly.at")

        user = create_test_user(email="admin@example.com")
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role=Role.admin.value)
        _ensure_subscription(
            db,
            group.id,
            tier=SubscriptionTier.pro.value,
            stripe_subscription_id="sub_fail",
            stripe_customer_id="cus_fail",
        )

        event = SimpleNamespace(
            id="evt_pay_fail_1",
            type="invoice.payment_failed",
            data=SimpleNamespace(
                object=SimpleNamespace(
                    subscription="sub_fail",
                    metadata={"group_id": str(group.id)},
                )
            ),
        )
        stripe_sub = SimpleNamespace(
            id="sub_fail",
            customer="cus_fail",
            status="past_due",
            metadata={"group_id": str(group.id)},
            object="subscription",
            items=SimpleNamespace(
                data=[
                    SimpleNamespace(
                        price=SimpleNamespace(
                            id="price_pro_monthly",
                            metadata={"tier": "pro"},
                            product=SimpleNamespace(metadata={}),
                        )
                    )
                ]
            ),
            current_period_end=None,
            cancel_at_period_end=False,
            trial_end=None,
        )

        with (
            patch(
                "app.services.billing.webhooks.construct_event",
                return_value=event,
            ),
            patch(
                "app.services.billing.webhooks.stripe_client.retrieve_subscription",
                return_value=stripe_sub,
            ),
            patch(
                "app.services.billing.notifications.send_payment_failed_email",
                new_callable=AsyncMock,
            ) as send_mail,
        ):
            response = await client.post(
                "/webhooks/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )

        assert response.status_code == 200
        send_mail.assert_awaited_once()
        assert send_mail.await_args.args[0] == "admin@example.com"
        assert "/settings/billing" in send_mail.await_args.kwargs["billing_url"]

        assert (
            db.query(BillingEvent)
            .filter(BillingEvent.stripe_event_id == "evt_pay_fail_1")
            .count()
            == 1
        )
