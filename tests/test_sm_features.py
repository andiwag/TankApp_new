"""Tests for S/M effort features: audit UI, export, partial fill, cost, analytics, rate limit."""

import csv
import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from app.models import AuditLog, FuelEntry
from app.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.services.analytics import get_analytics_context
from app.services.consumption import average_consumption_for_vehicle
from app.services.export import fuel_entries_csv, vehicles_csv
from app.services.summary import get_summary_context

from tests.conftest import create_authenticated_group


class TestPartialFillConsumption:
    def test_partial_fill_excluded_from_consumption_segments(self):
        with_partial = [
            (100.0, 40.0, True),
            (150.0, 5.0, False),
            (200.0, 10.0, True),
        ]
        all_full = [
            (100.0, 40.0, True),
            (150.0, 5.0, True),
            (200.0, 10.0, True),
        ]
        assert average_consumption_for_vehicle("km", with_partial) == pytest.approx(
            10.0
        )
        assert average_consumption_for_vehicle("km", all_full) == pytest.approx(15.0)


class TestCostTracking:
    def test_summary_includes_vehicle_and_group_costs(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=50.0,
            usage_reading=1000.0,
            entry_date=date.today(),
        )
        entry = db.query(FuelEntry).one()
        entry.total_cost_eur = 75.50
        db.commit()

        ctx = get_summary_context(db, group.id)
        vehicle_row = next(
            r for r in ctx["vehicle_rows"] if r["vehicle_id"] == vehicle.id
        )
        assert vehicle_row["total_cost_eur"] == pytest.approx(75.50)
        assert ctx["total_group_cost_eur"] == pytest.approx(75.50)


class TestExportCsv:
    def test_fuel_entries_csv_includes_new_columns(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user(name="Alice Export")
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, name="Tractor 1")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=42.0,
            usage_reading=500.0,
            entry_date=date(2025, 3, 15),
        )
        entry = db.query(FuelEntry).one()
        entry.full_tank = False
        entry.total_cost_eur = 63.0
        db.commit()

        content = fuel_entries_csv(db, group.id)
        rows = list(csv.reader(io.StringIO(content)))
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
        assert rows[1][1] == "Tractor 1"
        assert rows[1][4] == "False"
        assert rows[1][5] == "63.0"
        assert rows[1][6] == "Alice Export"

    def test_vehicles_csv_lists_group_vehicles(
        self, db, create_test_group, create_test_vehicle
    ):
        group = create_test_group()
        create_test_vehicle(group_id=group.id, name="Combine")

        content = vehicles_csv(db, group.id)
        rows = list(csv.reader(io.StringIO(content)))
        assert rows[0] == ["name", "type", "usage_unit", "fuel_type", "created_at"]
        assert rows[1][0] == "Combine"


class TestExportRoutes:
    async def test_export_fuel_entries_csv_route(self, client, auth_group):
        auth_group()
        response = await client.get("/export/fuel-entries.csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "fuel-entries.csv" in response.headers.get("content-disposition", "")
        assert "date,vehicle,fuel_liters" in response.text.splitlines()[0]

    async def test_export_vehicles_csv_route(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group()
        create_test_vehicle(group_id=group.id, name="Exported")
        response = await client.get("/export/vehicles.csv")
        assert response.status_code == 200
        assert "vehicles.csv" in response.headers.get("content-disposition", "")
        assert "Exported" in response.text


class TestAuditLogUi:
    async def test_admin_can_view_audit_log_page(
        self, client, auth_group, create_test_user, db
    ):
        user, group = auth_group(role="admin")
        db.add(
            AuditLog(
                group_id=group.id,
                user_id=user.id,
                action="vehicle.create",
                entity_type="vehicle",
                entity_id=1,
            )
        )
        db.commit()

        response = await client.get("/settings/audit")
        assert response.status_code == 200
        assert "Änderungsprotokoll" in response.text
        assert "vehicle.create" in response.text

    async def test_viewer_cannot_view_audit_log_page(self, client, auth_group):
        auth_group(role="reader")
        response = await client.get("/settings/audit")
        assert response.status_code == 403

    async def test_group_settings_links_audit_log_for_admin(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert "/settings/audit" in response.text


class TestAnalyticsDashboard:
    def test_analytics_context_builds_chart_data(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, name="Chart Tractor")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=30.0,
            usage_reading=100.0,
        )
        entry = db.query(FuelEntry).one()
        entry.total_cost_eur = 45.0
        db.commit()

        ctx = get_analytics_context(db, group.id)
        assert len(ctx["vehicle_chart"]) == 1
        assert ctx["vehicle_chart"][0]["name"] == "Chart Tractor"
        assert ctx["vehicle_chart"][0]["liters"] == 30.0
        assert ctx["has_cost_data"] is True
        assert any(m["cost_eur"] == 45.0 for m in ctx["monthly_chart"])

    def test_analytics_vehicle_chart_uses_rolling_12_month_window(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, name="Window Tractor")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=100.0,
            entry_date=date(2026, 6, 1),
        )
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=90.0,
            usage_reading=200.0,
            entry_date=date(2025, 5, 31),
        )

        ctx = get_analytics_context(db, group.id, today=date(2026, 6, 15))

        assert ctx["vehicle_chart"] == [{"name": "Window Tractor", "liters": 40.0}]

    async def test_analytics_page_renders(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group()
        create_test_vehicle(group_id=group.id)
        response = await client.get("/analytics")
        assert response.status_code == 200
        assert "Einblicke" in response.text
        assert "vehicle-chart" in response.text
        assert "chart.umd.min.js" in response.text


class TestFuelEntryFeatures:
    async def test_create_partial_fill_with_cost(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        vehicle = create_test_vehicle(group_id=group.id)
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(vehicle.id),
                "fuel_amount_l": "25",
                "usage_reading": "1000",
                "entry_date": date.today().isoformat(),
                "notes": "",
                "full_tank": "0",
                "total_cost_eur": "37.50",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        entry = db.query(FuelEntry).one()
        assert entry.full_tank is False
        assert entry.total_cost_eur == pytest.approx(37.50)


class TestRateLimiters:
    def test_in_memory_rate_limiter_blocks_after_max_attempts(self):
        limiter = InMemoryRateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            limiter.record_attempt("user:1")
        assert limiter.is_limited("user:1") is True

    def test_in_memory_rate_limiter_clear_resets(self):
        limiter = InMemoryRateLimiter(max_attempts=2, window_seconds=60)
        limiter.record_attempt("user:1")
        limiter.record_attempt("user:1")
        limiter.clear("user:1")
        assert limiter.is_limited("user:1") is False

    def test_redis_rate_limiter_uses_sorted_set(self):
        import sys

        mock_client = MagicMock()
        mock_client.pipeline.return_value = mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [1, 0, True]
        mock_redis_module = MagicMock()
        mock_redis_module.from_url.return_value = mock_client

        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            limiter = RedisRateLimiter(
                redis_url="redis://localhost:6379/0",
                max_attempts=5,
                window_seconds=60,
            )

        limiter.record_attempt("login:1@example.com")
        mock_client.pipeline.assert_called()
        mock_pipe.zadd.assert_called_once()
        mock_pipe.zremrangebyscore.assert_called_once()
        mock_pipe.expire.assert_called_once()
