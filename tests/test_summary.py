"""Tests for Phase 11: Summary & statistics."""

import re
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from app.models import FuelEntry, Vehicle
from app.services.consumption import (
    average_consumption_for_vehicle,
    consumption_unit_label,
)
from app.services.summary import get_summary_context


def _find_vehicle_liters(html: str, vehicle_id: int) -> float:
    m = re.search(
        rf'id="sum-liters-{vehicle_id}">([\d.]+)</', html,
    )
    assert m is not None, f"missing sum-liters-{vehicle_id}"
    return float(m.group(1))


def _find_vehicle_count(html: str, vehicle_id: int) -> int:
    m = re.search(rf'id="sum-count-{vehicle_id}">(\d+)</', html)
    assert m is not None, f"missing sum-count-{vehicle_id}"
    return int(m.group(1))


def _month_liters(html: str, year: int, month: int) -> float:
    m = re.search(
        rf'id="sum-month-{year:d}-{month:02d}">([\d.]+)</', html,
    )
    assert m is not None, f"missing sum-month-{year}-{month:02d}"
    return float(m.group(1))


# ── Pure consumption (D-004) ─────────────────────────────────────────────────


class TestConsumptionCalculation:
    def test_consumption_car_two_entries_calculates_l_per_100km(self):
        # First fill at 10000 km (ignored for segments); second fill 5 L over 100 km
        r = average_consumption_for_vehicle(
            "km", [(10000, 40.0), (10100, 5.0)]
        )
        assert r == pytest.approx(5.0)

    def test_consumption_tractor_two_entries_calculates_l_per_hour(self):
        r = average_consumption_for_vehicle(
            "hours", [(10.0, 0.0), (20.0, 3.0)]
        )
        assert r == pytest.approx(0.3)

    def test_consumption_single_entry_no_result(self):
        assert average_consumption_for_vehicle("km", [(100.0, 10.0)]) is None

    def test_consumption_three_entries_calculates_average(self):
        r = average_consumption_for_vehicle(
            "km",
            [(100.0, 0.0), (200.0, 10.0), (400.0, 15.0)],
        )
        assert r == pytest.approx(8.75)

    def test_consumption_sorts_by_usage_reading_not_date(self):
        r = average_consumption_for_vehicle(
            "km",
            [(400.0, 15.0), (100.0, 0.0), (200.0, 10.0)],
        )
        assert r == pytest.approx(8.75)

    def test_consumption_handles_large_gap_in_readings(self):
        r = average_consumption_for_vehicle(
            "km", [(0.0, 0.0), (100_000.0, 50.0)]
        )
        assert r == pytest.approx(50.0 / 100_000.0 * 100.0)

    def test_consumption_unit_label_km_and_hours(self):
        assert consumption_unit_label("km") == "L/100 km"
        assert consumption_unit_label("hours") == "L/h"

    def test_consumption_unit_label_unknown(self):
        assert consumption_unit_label("bogus") == "—"


# ── Summary context (DB) ─────────────────────────────────────────────────────


class TestSummaryFuelPerVehicle:
    def test_summary_fuel_per_vehicle_total_liters(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id, name="V1")
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=20.0
        )
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=30.0
        )
        ctx = get_summary_context(db, group.id, today=date(2026, 6, 1))
        row = next(x for x in ctx["vehicle_rows"] if x["vehicle_id"] == v.id)
        assert row["total_liters"] == pytest.approx(50.0)

    def test_summary_fuel_per_vehicle_entry_count(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        for _ in range(3):
            create_test_fuel_entry(
                vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=1.0
            )
        ctx = get_summary_context(db, group.id, today=date(2026, 6, 1))
        row = next(x for x in ctx["vehicle_rows"] if x["vehicle_id"] == v.id)
        assert row["entry_count"] == 3

    def test_summary_fuel_per_vehicle_excludes_soft_deleted_entries(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=10.0
        )
        e2 = create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=90.0
        )
        db.query(FuelEntry).filter(FuelEntry.id == e2.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()
        ctx = get_summary_context(db, group.id, today=date(2026, 6, 1))
        row = next(x for x in ctx["vehicle_rows"] if x["vehicle_id"] == v.id)
        assert row["total_liters"] == pytest.approx(10.0)
        assert row["entry_count"] == 1

    def test_summary_fuel_per_vehicle_excludes_soft_deleted_vehicles(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v_ok = create_test_vehicle(group_id=group.id, name="OK")
        v_gone = create_test_vehicle(group_id=group.id, name="Gone")
        create_test_fuel_entry(
            vehicle_id=v_ok.id, group_id=group.id, user_id=user.id, fuel_amount_l=5.0
        )
        create_test_fuel_entry(
            vehicle_id=v_gone.id, group_id=group.id, user_id=user.id, fuel_amount_l=100.0
        )
        db.query(Vehicle).filter(Vehicle.id == v_gone.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()
        ctx = get_summary_context(db, group.id, today=date(2026, 6, 1))
        ids = {r["vehicle_id"] for r in ctx["vehicle_rows"]}
        assert v_ok.id in ids
        assert v_gone.id not in ids

    def test_summary_fuel_per_vehicle_scoped_to_active_group(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAA11", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBB11", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="admin")
        create_test_user_group(user.id, g_b.id, role="admin")
        va = create_test_vehicle(group_id=g_a.id)
        vb = create_test_vehicle(group_id=g_b.id)
        create_test_fuel_entry(
            vehicle_id=va.id, group_id=g_a.id, user_id=user.id, fuel_amount_l=10.0
        )
        create_test_fuel_entry(
            vehicle_id=vb.id, group_id=g_b.id, user_id=user.id, fuel_amount_l=999.0
        )
        ctx_a = get_summary_context(db, g_a.id, today=date(2026, 6, 1))
        liters_a = sum(r["total_liters"] for r in ctx_a["vehicle_rows"])
        assert liters_a == pytest.approx(10.0)

    def test_consumption_excludes_soft_deleted_entries(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        """Soft-deleted fills are omitted when building consumption segments."""
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id, vtype="car")
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=10.0,
            usage_reading=100.0,
        )
        e_mid = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=999.0,
            usage_reading=200.0,
        )
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=30.0,
            usage_reading=400.0,
        )
        db.query(FuelEntry).filter(FuelEntry.id == e_mid.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()
        ctx = get_summary_context(db, group.id, today=date(2026, 6, 1))
        row = next(x for x in ctx["vehicle_rows"] if x["vehicle_id"] == v.id)
        # Only segment 100→400 with 30 L: 30/300*100 = 10 L/100km
        assert row["avg_consumption"] == pytest.approx(10.0)


class TestSummaryMonthly:
    @patch("app.services.summary._today", return_value=date(2026, 6, 15))
    def test_summary_monthly_totals_last_12_months(
        self,
        _mock_today,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=100.0,
            entry_date=date(2026, 6, 10),
        )
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            entry_date=date(2026, 5, 5),
        )
        ctx = get_summary_context(db, group.id)
        months = {m["key"]: m["liters"] for m in ctx["monthly_rows"]}
        assert months.get((2026, 6), 0.0) == pytest.approx(100.0)
        assert months.get((2026, 5), 0.0) == pytest.approx(40.0)

    @patch("app.services.summary._today", return_value=date(2026, 6, 15))
    def test_summary_monthly_totals_empty_months_show_zero(
        self,
        _mock_today,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=10.0,
            entry_date=date(2026, 6, 1),
        )
        ctx = get_summary_context(db, group.id)
        months = {m["key"]: m["liters"] for m in ctx["monthly_rows"]}
        assert len(months) == 12
        assert months.get((2025, 7), None) == 0.0

    def test_summary_monthly_totals_excludes_soft_deleted(
        self, db, create_test_user, create_test_group, create_test_user_group,
        create_test_vehicle, create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=50.0,
            entry_date=date(2026, 3, 1),
        )
        e2 = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=50.0,
            entry_date=date(2026, 3, 15),
        )
        db.query(FuelEntry).filter(FuelEntry.id == e2.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()
        ctx = get_summary_context(db, group.id, today=date(2026, 6, 1))
        months = {m["key"]: m["liters"] for m in ctx["monthly_rows"]}
        assert months.get((2026, 3), 0.0) == pytest.approx(50.0)


# ── HTTP ─────────────────────────────────────────────────────────────────────


class TestSummaryPageAuth:
    @pytest.mark.asyncio
    async def test_summary_requires_auth(self, client):
        r = await client.get("/summary", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers.get("location") == "/login"

    @pytest.mark.asyncio
    async def test_summary_requires_active_group(self, client, create_test_user, auth_cookie):
        user = create_test_user()
        auth_cookie(client, user.id, active_group_id=None)
        r = await client.get("/summary", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers.get("location") == "/groups"


class TestSummaryPageContent:
    @pytest.mark.asyncio
    async def test_summary_fuel_per_vehicle_total_liters(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=25.0
        )
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=25.0
        )
        auth_cookie(client, user.id, group.id)
        r = await client.get("/summary")
        assert r.status_code == 200
        assert _find_vehicle_liters(r.text, v.id) == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_summary_fuel_per_vehicle_entry_count(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=1.0
        )
        auth_cookie(client, user.id, group.id)
        r = await client.get("/summary")
        assert _find_vehicle_count(r.text, v.id) == 1

    @pytest.mark.asyncio
    @patch("app.services.summary._today", return_value=date(2026, 6, 15))
    async def test_summary_monthly_totals_last_12_months(
        self,
        _mock_today,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=33.0,
            entry_date=date(2026, 6, 1),
        )
        auth_cookie(client, user.id, group.id)
        r = await client.get("/summary")
        assert r.status_code == 200
        assert _month_liters(r.text, 2026, 6) == pytest.approx(33.0)

    @pytest.mark.asyncio
    async def test_summary_empty_group_shows_no_data_message(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)
        r = await client.get("/summary")
        assert r.status_code == 200
        assert 'id="summary-empty-state"' in r.text
