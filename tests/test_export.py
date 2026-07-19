"""Tests for Phase 28: extended CSV exports."""

import csv
import io
from datetime import date

from app.enums import FillSource
from app.schemas import (
    FuelEntryCreate,
    TankDeliveryCreate,
    TankExternalWithdrawalCreate,
)
from app.services.export import fuel_entries_csv, tank_ledger_csv
from app.services.fuel_entries import create_fuel_entry
from app.services.tank_ledger import post_delivery, post_external_withdrawal


class TestFuelEntriesExport:
    def test_export_fuel_entries_includes_fill_source_and_tank_name(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, fuel_type="diesel")
        tank = create_test_storage_tank(
            group_id=group.id, name="Hof Diesel", opening_balance_l=500.0
        )
        create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=40.0,
                usage_reading=100.0,
                entry_date=date(2025, 4, 1),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
            ),
        )

        rows = list(csv.reader(io.StringIO(fuel_entries_csv(db, group.id))))

        assert rows[0] == [
            "date",
            "vehicle",
            "fuel_liters",
            "usage_reading",
            "full_tank",
            "total_cost_eur",
            "logged_by",
            "notes",
            "adblue_liters",
            "fill_source",
            "fuel_tank_name",
        ]
        assert rows[1][9] == "farm"
        assert rows[1][10] == "Hof Diesel"


class TestTankLedgerExport:
    def test_export_tank_ledger_csv_scoped_to_group(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        g_a = create_test_group(
            name="Farm A", invite_code="FARM-AAAA1", created_by=user.id
        )
        g_b = create_test_group(
            name="Farm B", invite_code="FARM-BBBB1", created_by=user.id
        )
        tank_a = create_test_storage_tank(
            group_id=g_a.id, name="Tank A", opening_balance_l=0.0
        )
        tank_b = create_test_storage_tank(
            group_id=g_b.id, name="Tank B", opening_balance_l=0.0
        )
        post_delivery(
            db,
            user.id,
            g_a.id,
            tank_a,
            TankDeliveryCreate(amount_l=100.0, entry_date=date(2025, 1, 1)),
        )
        post_external_withdrawal(
            db,
            user.id,
            g_b.id,
            tank_b,
            TankExternalWithdrawalCreate(
                amount_l=30.0,
                entry_date=date(2025, 2, 1),
                recipient_name="Secret",
            ),
        )

        rows_a = list(csv.reader(io.StringIO(tank_ledger_csv(db, g_a.id))))
        rows_b = list(csv.reader(io.StringIO(tank_ledger_csv(db, g_b.id))))

        assert len(rows_a) == 2
        assert rows_a[1][1] == "Tank A"
        assert "Secret" not in "\n".join(",".join(r) for r in rows_a)

        assert len(rows_b) == 2
        assert rows_b[1][1] == "Tank B"
        assert rows_b[1][4] == "Secret"
