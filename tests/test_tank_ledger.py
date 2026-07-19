"""Tests for Phase 25: tank ledger and stock calculation."""

from datetime import date

import pytest
from app.models import TankLedgerEntry
from app.schemas import TankAdjustmentCreate, TankDeliveryCreate
from app.services.tank_ledger import (
    current_stock_l,
    post_adjustment,
    post_delivery,
)
from app.time_utils import utc_now
from pydantic import ValidationError

from tests.conftest import create_authenticated_group


class TestCurrentStock:
    def test_current_stock_opening_balance_only(
        self, db, create_test_group, create_test_storage_tank
    ):
        group = create_test_group()
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=750.0)
        assert current_stock_l(db, tank) == pytest.approx(750.0)

    def test_current_stock_includes_deliveries(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        post_delivery(
            db,
            user.id,
            group.id,
            tank,
            TankDeliveryCreate(
                amount_l=250.0,
                entry_date=date.today(),
            ),
        )
        db.refresh(tank)
        assert current_stock_l(db, tank) == pytest.approx(350.0)

    def test_current_stock_excludes_soft_deleted_ledger_rows(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=0.0)
        post_delivery(
            db,
            user.id,
            group.id,
            tank,
            TankDeliveryCreate(amount_l=100.0, entry_date=date.today()),
        )
        entry = db.query(TankLedgerEntry).one()
        entry.deleted_at = utc_now()
        db.commit()
        assert current_stock_l(db, tank) == pytest.approx(0.0)


class TestTankLedgerMutations:
    def test_delivery_creates_positive_ledger_entry(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id)
        post_delivery(
            db,
            user.id,
            group.id,
            tank,
            TankDeliveryCreate(amount_l=42.0, entry_date=date(2025, 1, 15)),
        )
        entry = db.query(TankLedgerEntry).one()
        assert entry.movement_type == "delivery"
        assert entry.amount_l == 42.0
        assert entry.group_id == group.id

    def test_adjustment_requires_notes(self):
        with pytest.raises(ValidationError):
            TankAdjustmentCreate(
                amount_l=-10.0,
                entry_date=date.today(),
                notes="",
            )

    async def test_adjustment_admin_only(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        tank = create_test_storage_tank(group_id=group.id)
        auth_cookie(client, user.id, group.id)
        response = await client.post(
            f"/tanks/{tank.id}/adjustment/new",
            data={
                "amount_l": "-5",
                "entry_date": date.today().isoformat(),
                "notes": "Korrektur",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403

    def test_adjustment_allows_negative_amount(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=200.0)
        post_adjustment(
            db,
            user.id,
            group.id,
            tank,
            TankAdjustmentCreate(
                amount_l=-50.0,
                entry_date=date.today(),
                notes="Manuelle Korrektur",
            ),
        )
        assert current_stock_l(db, tank) == pytest.approx(150.0)

    def test_negative_stock_computed_allowed(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=50.0)
        post_adjustment(
            db,
            user.id,
            group.id,
            tank,
            TankAdjustmentCreate(
                amount_l=-100.0,
                entry_date=date.today(),
                notes="Überziehung",
            ),
        )
        assert current_stock_l(db, tank) == pytest.approx(-50.0)

    def test_ledger_entry_group_id_must_match_tank_group(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAA01", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBB01", created_by=user.id)
        tank = create_test_storage_tank(group_id=g_a.id)
        with pytest.raises(ValueError, match="Gruppe"):
            post_delivery(
                db,
                user.id,
                g_b.id,
                tank,
                TankDeliveryCreate(amount_l=10.0, entry_date=date.today()),
            )

    async def test_delivery_via_post_route(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=0.0)
        response = await client.post(
            f"/tanks/{tank.id}/delivery/new",
            data={
                "amount_l": "120",
                "entry_date": date.today().isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert current_stock_l(db, tank) == pytest.approx(120.0)
