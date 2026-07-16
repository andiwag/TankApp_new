"""Tests for Stripe billing and entitlement enforcement."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.config import settings
from app.enums import Role, SubscriptionTier
from app.main import app
from app.models import BillingEvent, Group, GroupSubscription
from app.services.billing.price_catalog import CatalogPrice, clear_catalog_cache
from httpx import ASGITransport, AsyncClient


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


def _ensure_subscription(
    db,
    group_id: int,
    *,
    tier: str = SubscriptionTier.free.value,
    status: str = "active",
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> GroupSubscription:
    sub = GroupSubscription(
        group_id=group_id,
        tier=tier,
        status=status,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    db.add(sub)
    group = db.query(Group).filter(Group.id == group_id).one()
    group.subscription_tier = tier
    db.commit()
    return sub


def _stripe_sub_with_tier(group_id: int, *, tier: str = "pro", status: str = "active"):
    return SimpleNamespace(
        id="sub_test",
        customer="cus_test",
        status=status,
        metadata={"group_id": str(group_id)},
        object="subscription",
        items=SimpleNamespace(
            data=[
                SimpleNamespace(
                    price=SimpleNamespace(
                        id="price_pro_monthly",
                        metadata={"tier": tier},
                        product=SimpleNamespace(metadata={}),
                    )
                )
            ]
        ),
        current_period_end=None,
        cancel_at_period_end=False,
        trial_end=None,
    )


class TestBillingPageAccess:
    async def test_billing_page_requires_auth(self, client):
        response = await client.get("/settings/billing", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    async def test_non_admin_cannot_access_billing(
        self,
        client,
        auth_group,
    ):
        auth_group(role=Role.contributor.value)
        response = await client.get("/settings/billing")
        assert response.status_code == 403

    async def test_admin_can_access_billing(
        self,
        client,
        auth_group,
        db,
        stripe_catalog,
    ):
        _, group = auth_group(role=Role.admin.value)
        _ensure_subscription(db, group.id)
        response = await client.get("/settings/billing")
        assert response.status_code == 200
        assert "Abo" in response.text or "Free" in response.text


class TestCheckoutSession:
    async def test_checkout_creates_session_with_group_metadata(
        self,
        client,
        auth_group,
        db,
        stripe_settings,
        stripe_catalog,
    ):
        user, group = auth_group(role=Role.admin.value)
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
        assert response.headers.get("location") == mock_session.url
        create_checkout.assert_called_once()
        call_kwargs = create_checkout.call_args.kwargs
        assert call_kwargs["group"].id == group.id
        assert call_kwargs["user"].id == user.id
        assert call_kwargs["price_id"] == "price_pro_monthly"

    async def test_checkout_rejects_unknown_lookup_key(
        self,
        client,
        auth_group,
        db,
        stripe_settings,
        stripe_catalog,
    ):
        _, group = auth_group(role=Role.admin.value)
        _ensure_subscription(db, group.id)

        response = await client.post(
            "/settings/billing/checkout",
            data={"lookup_key": "unknown_key"},
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_checkout_blocked_when_active_subscription_exists(
        self,
        client,
        auth_group,
        db,
        stripe_settings,
        stripe_catalog,
    ):
        _, group = auth_group(role=Role.admin.value)
        _ensure_subscription(
            db,
            group.id,
            tier=SubscriptionTier.pro.value,
            status="active",
            stripe_subscription_id="sub_active",
            stripe_customer_id="cus_active",
        )

        with patch(
            "app.services.billing.stripe_client.create_checkout_session",
        ) as create_checkout:
            response = await client.post(
                "/settings/billing/checkout",
                data={"lookup_key": settings.STRIPE_LOOKUP_FARM_MONTHLY},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers.get("location") == "/settings/billing"
        create_checkout.assert_not_called()


class TestWebhookHandling:
    async def test_webhook_invalid_signature_returns_400(
        self,
        stripe_settings,
    ):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            with patch(
                "app.services.billing.webhooks.construct_event",
                side_effect=ValueError("Invalid signature"),
            ):
                response = await ac.post(
                    "/webhooks/stripe",
                    content=b"{}",
                    headers={"Stripe-Signature": "bad"},
                )
        assert response.status_code == 400

    async def test_webhook_idempotency(
        self,
        db,
        create_test_group,
        stripe_settings,
    ):
        from app.services.billing.webhooks import process_stripe_webhook

        group = create_test_group()
        event = SimpleNamespace(
            id="evt_test_123",
            type="customer.subscription.deleted",
            data=SimpleNamespace(
                object=SimpleNamespace(
                    id="sub_test",
                    object="subscription",
                    metadata={"group_id": str(group.id)},
                    status="canceled",
                    items=SimpleNamespace(data=[]),
                    current_period_end=None,
                    cancel_at_period_end=False,
                    trial_end=None,
                    customer="cus_test",
                )
            ),
        )

        with patch(
            "app.services.billing.webhooks.construct_event",
            return_value=event,
        ), patch(
            "app.services.billing.webhooks.stripe_client.retrieve_subscription",
            return_value=_stripe_sub_with_tier(group.id, status="canceled"),
        ):
            process_stripe_webhook(db, b"{}", "sig")
            process_stripe_webhook(db, b"{}", "sig")

        count = (
            db.query(BillingEvent)
            .filter(BillingEvent.stripe_event_id == "evt_test_123")
            .count()
        )
        assert count == 1

    async def test_subscription_updated_re_fetches_from_stripe(
        self,
        db,
        create_test_group,
        stripe_settings,
    ):
        from app.services.billing.webhooks import dispatch_event

        group = create_test_group()
        _ensure_subscription(db, group.id, tier=SubscriptionTier.free.value)
        event = SimpleNamespace(
            type="customer.subscription.updated",
            data=SimpleNamespace(
                object=SimpleNamespace(
                    id="sub_live",
                    object="subscription",
                    metadata={"group_id": str(group.id)},
                )
            ),
        )
        stripe_sub = _stripe_sub_with_tier(group.id, tier="pro")

        with patch(
            "app.services.billing.webhooks.stripe_client.retrieve_subscription",
            return_value=stripe_sub,
        ) as retrieve:
            dispatch_event(db, event)

        retrieve.assert_called_once_with("sub_live")
        sub = db.query(GroupSubscription).filter_by(group_id=group.id).one()
        assert sub.tier == SubscriptionTier.pro.value

    async def test_webhook_ignores_invalid_group_id(
        self,
        db,
        stripe_settings,
    ):
        from app.services.billing.webhooks import process_stripe_webhook

        event = SimpleNamespace(
            id="evt_bad_meta",
            type="customer.subscription.updated",
            data=SimpleNamespace(
                object=SimpleNamespace(
                    id="sub_bad",
                    object="subscription",
                    metadata={"group_id": "not-a-number"},
                    status="active",
                    items=SimpleNamespace(data=[]),
                    customer="cus_test",
                )
            ),
        )

        with patch(
            "app.services.billing.webhooks.construct_event",
            return_value=event,
        ), patch(
            "app.services.billing.webhooks.stripe_client.retrieve_subscription",
            return_value=event.data.object,
        ) as retrieve:
            process_stripe_webhook(db, b"{}", "sig")
            retrieve.assert_called_once_with("sub_bad")

        assert (
            db.query(BillingEvent)
            .filter(BillingEvent.stripe_event_id == "evt_bad_meta")
            .count()
            == 1
        )

    async def test_subscription_deleted_resets_tier_to_free(
        self,
        db,
        create_test_group,
        stripe_settings,
    ):
        from app.services.billing.subscriptions import sync_subscription_from_stripe
        from app.services.billing.webhooks import process_stripe_webhook

        group = create_test_group()
        _ensure_subscription(
            db,
            group.id,
            tier=SubscriptionTier.pro.value,
            stripe_subscription_id="sub_test",
            stripe_customer_id="cus_test",
        )

        stripe_sub = _stripe_sub_with_tier(group.id, tier="pro", status="canceled")
        sync_subscription_from_stripe(db, stripe_sub, event_type="deleted")

        db.refresh(group)
        sub = db.query(GroupSubscription).filter_by(group_id=group.id).one()
        assert sub.tier == SubscriptionTier.free.value
        assert group.subscription_tier == SubscriptionTier.free.value

        event = SimpleNamespace(
            id="evt_del_1",
            type="customer.subscription.deleted",
            data=SimpleNamespace(object=stripe_sub),
        )
        with patch(
            "app.services.billing.webhooks.construct_event",
            return_value=event,
        ), patch(
            "app.services.billing.webhooks.stripe_client.retrieve_subscription",
            return_value=stripe_sub,
        ):
            process_stripe_webhook(db, b"{}", "sig")

        db.refresh(group)
        sub = db.query(GroupSubscription).filter_by(group_id=group.id).one()
        assert sub.tier == SubscriptionTier.free.value


class TestReconcile:
    def test_reconcile_group_subscription_fetches_stripe(
        self, db, create_test_group, stripe_settings
    ):
        from app.services.billing.subscriptions import reconcile_group_subscription

        group = create_test_group()
        _ensure_subscription(
            db,
            group.id,
            tier=SubscriptionTier.free.value,
            stripe_subscription_id="sub_reconcile",
        )
        stripe_sub = _stripe_sub_with_tier(group.id, tier="farm")

        with patch(
            "app.services.billing.stripe_client.retrieve_subscription",
            return_value=stripe_sub,
        ) as retrieve:
            reconcile_group_subscription(db, group.id)

        retrieve.assert_called_once_with("sub_reconcile")
        sub = db.query(GroupSubscription).filter_by(group_id=group.id).one()
        assert sub.tier == SubscriptionTier.farm.value


class TestEntitlementEnforcement:
    async def test_analytics_blocked_on_free_tier(
        self,
        client,
        auth_group,
        db,
    ):
        _, group = auth_group()
        _ensure_subscription(db, group.id, tier=SubscriptionTier.free.value)

        response = await client.get("/analytics", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/settings/billing"

    async def test_analytics_allowed_on_pro_tier(
        self,
        client,
        auth_group,
        db,
    ):
        _, group = auth_group()
        _ensure_subscription(db, group.id, tier=SubscriptionTier.pro.value)

        response = await client.get("/analytics")
        assert response.status_code == 200

    async def test_export_blocked_on_free_tier(
        self,
        client,
        auth_group,
        db,
    ):
        _, group = auth_group()
        _ensure_subscription(db, group.id, tier=SubscriptionTier.free.value)

        response = await client.get("/export/fuel-entries.csv")
        assert response.status_code == 403

    async def test_vehicle_create_blocked_at_free_limit(
        self,
        client,
        auth_group,
        db,
        create_test_vehicle,
    ):
        _, group = auth_group(role=Role.contributor.value)
        _ensure_subscription(db, group.id, tier=SubscriptionTier.free.value)
        create_test_vehicle(group_id=group.id, name="V1")
        create_test_vehicle(group_id=group.id, name="V2")

        response = await client.post(
            "/vehicles/new",
            data={"name": "V3", "vtype": "tractor", "fuel_type": "diesel"},
        )
        assert response.status_code == 200
        assert "Upgrade" in response.text or "Abo" in response.text or "Limit" in response.text


class TestGroupCreateSubscription:
    def test_create_group_creates_free_subscription(
        self, db, create_test_user
    ):
        from app.schemas import GroupCreate
        from app.services.groups import create_group

        user = create_test_user()
        group = create_group(db, user, GroupCreate(name="New Farm"))
        db.commit()

        sub = (
            db.query(GroupSubscription)
            .filter(GroupSubscription.group_id == group.id)
            .one()
        )
        assert sub.tier == SubscriptionTier.free.value
        assert sub.status == "active"

        db.refresh(group)
        assert group.subscription_tier == SubscriptionTier.free.value
