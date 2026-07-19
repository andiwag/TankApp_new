"""Tests for Phase 24: optional AdBlue on tractor fuel entries."""

import csv
import io
from datetime import date

import pytest
from app.models import FuelEntry
from app.schemas import FuelEntryCreate
from app.services.consumption import average_consumption_for_vehicle
from app.services.export import fuel_entries_csv
from app.services.fuel_entries import create_fuel_entry
from app.services.summary import get_summary_context
from pydantic import ValidationError

from tests.conftest import create_authenticated_group


class TestAdBlueValidation:
    def test_fuel_entry_create_with_adblue_on_tractor(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tractor = create_test_vehicle(group_id=group.id, vtype="tractor")
        data = FuelEntryCreate(
            vehicle_id=tractor.id,
            fuel_amount_l=50.0,
            usage_reading=100.0,
            entry_date=date.today(),
            adblue_amount_l=5.0,
        )
        entry = create_fuel_entry(db, user.id, group.id, tractor, data)
        assert entry.adblue_amount_l == 5.0

    def test_fuel_entry_create_without_adblue_on_tractor_ok(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tractor = create_test_vehicle(group_id=group.id, vtype="tractor")
        data = FuelEntryCreate(
            vehicle_id=tractor.id,
            fuel_amount_l=50.0,
            usage_reading=100.0,
            entry_date=date.today(),
        )
        entry = create_fuel_entry(db, user.id, group.id, tractor, data)
        assert entry.adblue_amount_l is None

    def test_fuel_entry_create_adblue_on_car_rejected(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        car = create_test_vehicle(group_id=group.id, vtype="car", fuel_type="petrol")
        data = FuelEntryCreate(
            vehicle_id=car.id,
            fuel_amount_l=30.0,
            usage_reading=1000.0,
            entry_date=date.today(),
            adblue_amount_l=2.0,
        )
        with pytest.raises(ValueError, match="Traktor"):
            create_fuel_entry(db, user.id, group.id, car, data)

    def test_fuel_entry_create_adblue_zero_rejected(self):
        with pytest.raises(ValidationError):
            FuelEntryCreate(
                vehicle_id=1,
                fuel_amount_l=50.0,
                usage_reading=100.0,
                entry_date=date.today(),
                adblue_amount_l=0,
            )


class TestAdBlueRoutes:
    async def test_fuel_entry_update_clears_adblue(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tractor = create_test_vehicle(group_id=group.id, vtype="tractor", name="T1")
        entry = create_test_fuel_entry(
            vehicle_id=tractor.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=200.0,
        )
        entry.adblue_amount_l = 3.5
        db.commit()

        response = await client.post(
            f"/fuel/{entry.id}/edit",
            data={
                "fuel_amount_l": "40",
                "usage_reading": "200",
                "entry_date": entry.entry_date.isoformat(),
                "adblue_amount_l": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(entry)
        assert entry.adblue_amount_l is None

    async def test_fuel_entry_form_shows_adblue_for_tractor_vehicle(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        create_test_vehicle(group_id=group.id, vtype="tractor", name="Traktor")
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        assert 'name="adblue_amount_l"' in response.text
        assert "AdBlue" in response.text

    async def test_fuel_entry_form_hides_adblue_for_car(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        create_test_vehicle(
            group_id=group.id, vtype="car", fuel_type="petrol", name="Auto"
        )
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        assert 'data-vtype="car"' in response.text
        assert 'x-model="selectedVehicleId"' in response.text
        assert 'x-show="isTractor()"' in response.text

    async def test_fuel_entry_edit_form_hides_adblue_for_car(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        car = create_test_vehicle(
            group_id=group.id, vtype="car", fuel_type="petrol", name="Auto"
        )
        entry = create_test_fuel_entry(
            vehicle_id=car.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=20.0,
            usage_reading=5000.0,
        )
        response = await client.get(f"/fuel/{entry.id}/edit")
        assert response.status_code == 200
        assert 'name="adblue_amount_l"' not in response.text

    async def test_create_fuel_entry_with_adblue_via_post(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tractor = create_test_vehicle(group_id=group.id, vtype="tractor")
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(tractor.id),
                "fuel_amount_l": "50",
                "usage_reading": "100",
                "entry_date": d.isoformat(),
                "adblue_amount_l": "4.5",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        entry = db.query(FuelEntry).one()
        assert entry.adblue_amount_l == pytest.approx(4.5)

    async def test_create_fuel_entry_adblue_on_car_via_post_rejected(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        car = create_test_vehicle(group_id=group.id, vtype="car", fuel_type="petrol")
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(car.id),
                "fuel_amount_l": "30",
                "usage_reading": "1000",
                "entry_date": d.isoformat(),
                "adblue_amount_l": "2",
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text
        assert db.query(FuelEntry).count() == 0


class TestAdBlueSummaryAndExport:
    def test_summary_includes_adblue_total_separate_from_fuel_liters(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tractor = create_test_vehicle(group_id=group.id, vtype="tractor")
        create_test_fuel_entry(
            vehicle_id=tractor.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=100.0,
            usage_reading=10.0,
        )
        entry = db.query(FuelEntry).one()
        entry.adblue_amount_l = 12.0
        db.commit()

        ctx = get_summary_context(db, group.id)
        row = next(r for r in ctx["vehicle_rows"] if r["vehicle_id"] == tractor.id)
        assert row["total_liters"] == pytest.approx(100.0)
        assert row["total_adblue_l"] == pytest.approx(12.0)
        assert ctx["total_group_adblue_l"] == pytest.approx(12.0)

    def test_consumption_ignores_adblue_amount(self):
        pairs = [(10.0, 50.0, True), (20.0, 30.0, True)]
        assert average_consumption_for_vehicle("hours", pairs) == pytest.approx(3.0)

    def test_export_csv_includes_adblue_column(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tractor = create_test_vehicle(group_id=group.id, name="JD")
        create_test_fuel_entry(
            vehicle_id=tractor.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=100.0,
            entry_date=date(2025, 6, 1),
        )
        entry = db.query(FuelEntry).one()
        entry.adblue_amount_l = 6.0
        db.commit()

        rows = list(csv.reader(io.StringIO(fuel_entries_csv(db, group.id))))
        assert "adblue_liters" in rows[0]
        adblue_idx = rows[0].index("adblue_liters")
        assert rows[1][adblue_idx] == "6.0"


class TestAdBlueFuelList:
    async def test_fuel_list_shows_adblue_badge(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tractor = create_test_vehicle(
            group_id=group.id, vtype="tractor", name="AdBlue Tractor"
        )
        entry = create_test_fuel_entry(
            vehicle_id=tractor.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=50.0,
            usage_reading=100.0,
        )
        entry.adblue_amount_l = 3.5
        db.commit()
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "AdBlue 3,50 L" in response.text or "AdBlue 3.50 L" in response.text
