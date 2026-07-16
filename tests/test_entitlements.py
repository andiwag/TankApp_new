"""Tests for subscription tier entitlements."""


from app.enums import SubscriptionTier
from app.models import GroupSubscription
from app.services.entitlements import (
    TIER_LIMITS,
    can_add_vehicle,
    effective_tier,
    get_group_tier,
    tier_has_feature,
    vehicle_limit_for_tier,
)


class TestTierLimits:
    def test_free_tier_limits(self):
        assert TIER_LIMITS[SubscriptionTier.free.value]["max_vehicles"] == 2
        assert tier_has_feature(SubscriptionTier.free.value, "analytics") is False
        assert tier_has_feature(SubscriptionTier.free.value, "export") is False
        assert tier_has_feature(SubscriptionTier.free.value, "maintenance") is False

    def test_pro_tier_limits(self):
        assert TIER_LIMITS[SubscriptionTier.pro.value]["max_vehicles"] == 10
        assert tier_has_feature(SubscriptionTier.pro.value, "analytics") is True

    def test_farm_tier_unlimited_vehicles(self):
        assert vehicle_limit_for_tier(SubscriptionTier.farm.value) is None


class TestGetGroupTier:
    def test_returns_free_when_no_subscription_row(
        self, db, create_test_group
    ):
        group = create_test_group()
        assert get_group_tier(db, group.id) == SubscriptionTier.free.value

    def test_returns_subscription_tier(
        self, db, create_test_group
    ):
        group = create_test_group()
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.pro.value,
                status="active",
            )
        )
        db.commit()
        assert get_group_tier(db, group.id) == SubscriptionTier.pro.value

    def test_past_due_keeps_paid_tier(
        self, db, create_test_group
    ):
        group = create_test_group()
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.pro.value,
                status="past_due",
            )
        )
        db.commit()
        assert effective_tier(db, group.id) == SubscriptionTier.pro.value


class TestCanAddVehicle:
    def test_free_allows_up_to_two_vehicles(
        self, db, create_test_group, create_test_vehicle
    ):
        group = create_test_group()
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.free.value,
                status="active",
            )
        )
        db.commit()
        create_test_vehicle(group_id=group.id, name="V1")
        create_test_vehicle(group_id=group.id, name="V2")
        assert can_add_vehicle(db, group.id) is False

    def test_free_allows_first_vehicle(
        self, db, create_test_group
    ):
        group = create_test_group()
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.free.value,
                status="active",
            )
        )
        db.commit()
        assert can_add_vehicle(db, group.id) is True

    def test_soft_deleted_vehicles_do_not_count(
        self, db, create_test_group, create_test_vehicle
    ):
        from app.time_utils import utc_now

        group = create_test_group()
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.free.value,
                status="active",
            )
        )
        db.commit()
        v1 = create_test_vehicle(group_id=group.id, name="V1")
        create_test_vehicle(group_id=group.id, name="V2")
        v1.deleted_at = utc_now()
        db.commit()
        assert can_add_vehicle(db, group.id) is True
