"""Tests for Phase 16: validation and polish."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from sqlalchemy import event

from tests.conftest import test_engine


@asynccontextmanager
async def _query_counter() -> AsyncIterator[list[str]]:
    statements: list[str] = []

    def _record_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", _record_query)
    try:
        yield statements
    finally:
        event.remove(test_engine, "before_cursor_execute", _record_query)


def _assert_has_submit_loading_state(html: str) -> None:
    assert "x-data" in html
    assert "@submit" in html
    assert ':disabled="submitting"' in html


class TestClientSideValidation:
    async def test_all_forms_have_required_field_validation(
        self, client, auth_group, create_test_vehicle
    ):
        _user, group = auth_group()
        vehicle = create_test_vehicle(group_id=group.id)

        pages = [
            "/login",
            "/register",
            "/forgot-password",
            "/groups",
            "/vehicles/new",
            f"/vehicles/{vehicle.id}/edit",
            "/fuel/new",
            "/profile",
        ]

        for path in pages:
            response = await client.get(path)
            assert response.status_code == 200, path
            html = response.text
            assert "required" in html, path
            _assert_has_submit_loading_state(html)

        register = (await client.get("/register")).text
        assert 'name="password" required minlength="8"' in register
        assert 'name="password_confirm" required minlength="8"' in register

        fuel_form = (await client.get("/fuel/new")).text
        assert 'name="fuel_amount_l"' in fuel_form
        assert 'type="number"' in fuel_form
        assert 'min="0.01"' in fuel_form
        assert 'step="0.01"' in fuel_form
        assert 'name="usage_reading"' in fuel_form
        assert 'min="0"' in fuel_form
        assert 'maxlength="500"' in fuel_form


class TestServerValidationMessages:
    async def test_server_validation_matches_schema_rules(
        self, client, auth_group, create_test_vehicle
    ):
        _user, group = auth_group()
        vehicle = create_test_vehicle(group_id=group.id)

        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(vehicle.id),
                "fuel_amount_l": "not-a-number",
                "usage_reading": "10",
                "entry_date": date.today().isoformat(),
            },
        )

        assert response.status_code == 200
        assert "Fuel amount must be a number" in response.text

        response = await client.post(
            "/register",
            data={
                "name": "Short Password",
                "email": "short-password@example.com",
                "password": "short",
                "password_confirm": "short",
            },
        )

        assert response.status_code == 200
        assert "Password must be at least 8 characters" in response.text


class TestFlashMessages:
    async def test_flash_messages_on_success_actions(self, client, auth_group):
        auth_group()

        response = await client.post(
            "/vehicles/new",
            data={"name": "Sprayer", "vtype": "machine", "fuel_type": "diesel"},
        )

        assert response.status_code == 303
        assert "tankly_flash" in response.cookies

    async def test_flash_messages_on_error_actions(self, client, create_test_user):
        create_test_user(email="existing@example.com")

        response = await client.post(
            "/register",
            data={
                "name": "Existing Email",
                "email": "existing@example.com",
                "password": "secret1234",
                "password_confirm": "secret1234",
            },
        )

        assert response.status_code == 200
        assert "Email already in use" in response.text
        assert "bg-red-50" in response.text


class TestQueryCounts:
    async def test_no_n_plus_1_queries_on_dashboard(
        self, client, auth_group, create_test_vehicle, create_test_fuel_entry
    ):
        user, group = auth_group()
        for i in range(10):
            vehicle = create_test_vehicle(group_id=group.id, name=f"Vehicle {i}")
            create_test_fuel_entry(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                fuel_amount_l=10 + i,
                usage_reading=100 + i,
            )

        async with _query_counter() as statements:
            response = await client.get("/dashboard")

        assert response.status_code == 200
        assert len(statements) <= 10

    async def test_no_n_plus_1_queries_on_vehicle_list(
        self, client, auth_group, create_test_vehicle
    ):
        _user, group = auth_group()
        for i in range(10):
            create_test_vehicle(group_id=group.id, name=f"Vehicle {i}")

        async with _query_counter() as statements:
            response = await client.get("/vehicles")

        assert response.status_code == 200
        assert len(statements) <= 6

    async def test_no_n_plus_1_queries_on_fuel_entry_list(
        self, client, auth_group, create_test_vehicle, create_test_fuel_entry
    ):
        user, group = auth_group()
        for i in range(10):
            vehicle = create_test_vehicle(group_id=group.id, name=f"Vehicle {i}")
            create_test_fuel_entry(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                fuel_amount_l=10 + i,
                usage_reading=100 + i,
            )

        async with _query_counter() as statements:
            response = await client.get("/fuel")

        assert response.status_code == 200
        assert len(statements) <= 6


class TestRateLimiting:
    async def test_login_route_is_rate_limited(self, client, create_test_user):
        create_test_user(email="limited@example.com", password="secret1234")

        for _ in range(5):
            response = await client.post(
                "/login",
                data={"email": "limited@example.com", "password": "wrongpass"},
            )
            assert response.status_code == 200

        response = await client.post(
            "/login",
            data={"email": "limited@example.com", "password": "wrongpass"},
        )

        assert response.status_code == 429
        assert "Too many attempts" in response.text
