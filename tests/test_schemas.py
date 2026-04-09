from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import (
    FuelEntryCreate,
    GroupCreate,
    PasswordChange,
    PasswordResetConfirm,
    UserCreate,
    VehicleCreate,
)


# ── UserCreate ───────────────────────────────────────────────────────────────


class TestUserCreate:
    def test_user_create_valid(self):
        u = UserCreate(
            email="alice@farm.com",
            name="Alice",
            password="secret1234",
            password_confirm="secret1234",
        )
        assert u.email == "alice@farm.com"
        assert u.name == "Alice"

    def test_user_create_password_mismatch_fails(self):
        with pytest.raises(ValidationError, match="[Pp]assword"):
            UserCreate(
                email="a@b.com",
                name="A",
                password="secret1234",
                password_confirm="different1",
            )

    def test_user_create_short_password_fails(self):
        with pytest.raises(ValidationError, match="[Pp]assword"):
            UserCreate(
                email="a@b.com",
                name="A",
                password="short",
                password_confirm="short",
            )

    def test_user_create_invalid_email_fails(self):
        with pytest.raises(ValidationError, match="[Ee]mail"):
            UserCreate(
                email="not-an-email",
                name="A",
                password="secret1234",
                password_confirm="secret1234",
            )

    def test_user_create_empty_name_fails(self):
        with pytest.raises(ValidationError, match="[Nn]ame"):
            UserCreate(
                email="a@b.com",
                name="",
                password="secret1234",
                password_confirm="secret1234",
            )


# ── VehicleCreate ────────────────────────────────────────────────────────────


class TestVehicleCreate:
    def test_vehicle_create_valid(self):
        v = VehicleCreate(name="Fendt 720", vtype="tractor", fuel_type="diesel")
        assert v.name == "Fendt 720"
        assert v.vtype == "tractor"
        assert v.fuel_type == "diesel"

    def test_vehicle_create_invalid_vtype_fails(self):
        with pytest.raises(ValidationError, match="vtype"):
            VehicleCreate(name="X", vtype="spaceship", fuel_type="diesel")

    def test_vehicle_create_invalid_fuel_type_fails(self):
        with pytest.raises(ValidationError, match="fuel_type"):
            VehicleCreate(name="X", vtype="car", fuel_type="hydrogen")


# ── FuelEntryCreate ──────────────────────────────────────────────────────────


class TestFuelEntryCreate:
    def test_fuel_entry_create_valid(self):
        e = FuelEntryCreate(
            vehicle_id=1,
            fuel_amount_l=45.5,
            usage_reading=12000.0,
            entry_date=date(2025, 6, 15),
        )
        assert e.fuel_amount_l == 45.5
        assert e.usage_reading == 12000.0

    def test_fuel_entry_create_negative_amount_fails(self):
        with pytest.raises(ValidationError, match="fuel_amount_l"):
            FuelEntryCreate(
                vehicle_id=1,
                fuel_amount_l=-10.0,
                usage_reading=100.0,
                entry_date=date(2025, 1, 1),
            )

    def test_fuel_entry_create_negative_reading_fails(self):
        with pytest.raises(ValidationError, match="usage_reading"):
            FuelEntryCreate(
                vehicle_id=1,
                fuel_amount_l=30.0,
                usage_reading=-5.0,
                entry_date=date(2025, 1, 1),
            )

    def test_fuel_entry_create_zero_amount_fails(self):
        with pytest.raises(ValidationError, match="fuel_amount_l"):
            FuelEntryCreate(
                vehicle_id=1,
                fuel_amount_l=0.0,
                usage_reading=100.0,
                entry_date=date(2025, 1, 1),
            )

    def test_fuel_entry_create_future_date_fails(self):
        future = date.today() + timedelta(days=1)
        with pytest.raises(ValidationError, match="entry_date"):
            FuelEntryCreate(
                vehicle_id=1,
                fuel_amount_l=30.0,
                usage_reading=100.0,
                entry_date=future,
            )


# ── GroupCreate ──────────────────────────────────────────────────────────────


class TestGroupCreate:
    def test_group_create_valid(self):
        g = GroupCreate(name="My Farm")
        assert g.name == "My Farm"

    def test_group_create_empty_name_fails(self):
        with pytest.raises(ValidationError, match="[Nn]ame"):
            GroupCreate(name="")


# ── PasswordChange ───────────────────────────────────────────────────────────


class TestPasswordChange:
    def test_password_change_mismatch_fails(self):
        with pytest.raises(ValidationError, match="[Pp]assword"):
            PasswordChange(
                current_password="oldpass123",
                new_password="newpass1234",
                new_password_confirm="different12",
            )


# ── PasswordResetConfirm ────────────────────────────────────────────────────


class TestPasswordResetConfirm:
    def test_password_reset_confirm_mismatch_fails(self):
        with pytest.raises(ValidationError, match="[Pp]assword"):
            PasswordResetConfirm(
                token="sometoken",
                new_password="newpass1234",
                new_password_confirm="different12",
            )
