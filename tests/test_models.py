from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, FuelEntry, Group, User, UserGroup, Vehicle


# ── User ─────────────────────────────────────────────────────────────────────


class TestUser:
    def test_create_user_valid(self, db):
        user = User(email="alice@farm.com", name="Alice", password_hash="hash123")
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.id is not None
        assert user.email == "alice@farm.com"
        assert user.name == "Alice"
        assert user.password_hash == "hash123"
        assert user.created_at is not None
        assert user.deleted_at is None

    def test_create_user_duplicate_email_fails(self, db):
        db.add(User(email="dup@farm.com", name="A", password_hash="h"))
        db.commit()

        db.add(User(email="dup@farm.com", name="B", password_hash="h"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_user_email_is_required(self, db):
        db.add(User(email=None, name="NoEmail", password_hash="h"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_user_name_is_required(self, db):
        db.add(User(email="noname@farm.com", name=None, password_hash="h"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_user_soft_delete_sets_deleted_at(self, db):
        user = User(email="del@farm.com", name="Del", password_hash="h")
        db.add(user)
        db.commit()

        user.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

        assert user.deleted_at is not None


# ── Group ────────────────────────────────────────────────────────────────────


class TestGroup:
    def test_create_group_valid(self, db, create_test_user):
        owner = create_test_user()
        group = Group(name="My Farm", invite_code="FARM-12345", created_by=owner.id)
        db.add(group)
        db.commit()
        db.refresh(group)

        assert group.id is not None
        assert group.name == "My Farm"
        assert group.invite_code == "FARM-12345"
        assert group.created_by == owner.id
        assert group.created_at is not None
        assert group.deleted_at is None
        assert group.subscription_tier is None

    def test_group_invite_code_unique(self, db, create_test_user):
        owner = create_test_user()
        db.add(Group(name="Farm A", invite_code="FARM-SAME1", created_by=owner.id))
        db.commit()

        db.add(Group(name="Farm B", invite_code="FARM-SAME1", created_by=owner.id))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_group_soft_delete(self, db, create_test_user):
        owner = create_test_user()
        group = Group(name="Farm", invite_code="FARM-DEL01", created_by=owner.id)
        db.add(group)
        db.commit()

        group.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(group)

        assert group.deleted_at is not None


# ── UserGroup ────────────────────────────────────────────────────────────────


class TestUserGroup:
    def test_create_user_group_valid(self, db, create_test_user, create_test_group):
        user = create_test_user()
        group = create_test_group(created_by=user.id)

        ug = UserGroup(user_id=user.id, group_id=group.id, role="admin")
        db.add(ug)
        db.commit()
        db.refresh(ug)

        assert ug.user_id == user.id
        assert ug.group_id == group.id
        assert ug.role == "admin"
        assert ug.joined_at is not None

    def test_user_group_composite_pk_prevents_duplicates(
        self, db, create_test_user, create_test_group
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)

        db.add(UserGroup(user_id=user.id, group_id=group.id, role="admin"))
        db.commit()

        db.add(UserGroup(user_id=user.id, group_id=group.id, role="reader"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_user_group_role_enum_values(
        self, db, create_test_user, create_test_group
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)

        for role in ("admin", "contributor", "reader"):
            db.rollback()
            ug = UserGroup(user_id=user.id, group_id=group.id, role=role)
            db.add(ug)
            db.commit()

            assert ug.role == role

            db.delete(ug)
            db.commit()


# ── Vehicle ──────────────────────────────────────────────────────────────────


class TestVehicle:
    def _setup(self, db, create_test_user, create_test_group):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        return group

    def test_create_vehicle_valid(
        self, db, create_test_user, create_test_group
    ):
        group = self._setup(db, create_test_user, create_test_group)
        vehicle = Vehicle(
            group_id=group.id, name="John Deere", vtype="tractor", fuel_type="diesel"
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

        assert vehicle.id is not None
        assert vehicle.name == "John Deere"
        assert vehicle.vtype == "tractor"
        assert vehicle.fuel_type == "diesel"
        assert vehicle.created_at is not None
        assert vehicle.deleted_at is None

    def test_vehicle_usage_unit_derived_from_vtype_car(
        self, db, create_test_user, create_test_group
    ):
        group = self._setup(db, create_test_user, create_test_group)
        v = Vehicle(group_id=group.id, name="VW Golf", vtype="car", fuel_type="petrol")
        db.add(v)
        db.commit()
        db.refresh(v)
        assert v.usage_unit == "km"

    def test_vehicle_usage_unit_derived_from_vtype_tractor(
        self, db, create_test_user, create_test_group
    ):
        group = self._setup(db, create_test_user, create_test_group)
        v = Vehicle(
            group_id=group.id, name="Fendt", vtype="tractor", fuel_type="diesel"
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        assert v.usage_unit == "hours"

    def test_vehicle_usage_unit_derived_from_vtype_motorcycle(
        self, db, create_test_user, create_test_group
    ):
        group = self._setup(db, create_test_user, create_test_group)
        v = Vehicle(
            group_id=group.id, name="BMW R1250", vtype="motorcycle", fuel_type="petrol"
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        assert v.usage_unit == "km"

    def test_vehicle_usage_unit_derived_from_vtype_machine(
        self, db, create_test_user, create_test_group
    ):
        group = self._setup(db, create_test_user, create_test_group)
        v = Vehicle(
            group_id=group.id, name="Harvester", vtype="machine", fuel_type="diesel"
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        assert v.usage_unit == "hours"

    def test_vehicle_belongs_to_group(
        self, db, create_test_user, create_test_group
    ):
        group = self._setup(db, create_test_user, create_test_group)
        v = Vehicle(
            group_id=group.id, name="Tractor", vtype="tractor", fuel_type="diesel"
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        assert v.group_id == group.id

    def test_vehicle_soft_delete(self, db, create_test_user, create_test_group):
        group = self._setup(db, create_test_user, create_test_group)
        v = Vehicle(
            group_id=group.id, name="Old Tractor", vtype="tractor", fuel_type="diesel"
        )
        db.add(v)
        db.commit()

        v.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(v)
        assert v.deleted_at is not None


# ── FuelEntry ────────────────────────────────────────────────────────────────


class TestFuelEntry:
    def _setup(self, db, create_test_user, create_test_group, create_test_vehicle):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        return user, group, vehicle

    def test_create_fuel_entry_valid(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user, group, vehicle = self._setup(
            db, create_test_user, create_test_group, create_test_vehicle
        )
        entry = FuelEntry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=45.5,
            usage_reading=1200.0,
            entry_date=date(2025, 6, 15),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        assert entry.id is not None
        assert entry.fuel_amount_l == 45.5
        assert entry.usage_reading == 1200.0
        assert entry.entry_date == date(2025, 6, 15)
        assert entry.created_at is not None
        assert entry.deleted_at is None

    def test_fuel_entry_group_id_matches_vehicle_group_id(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user, group, vehicle = self._setup(
            db, create_test_user, create_test_group, create_test_vehicle
        )
        entry = FuelEntry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=30.0,
            usage_reading=500.0,
            entry_date=date(2025, 6, 1),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        assert entry.group_id == vehicle.group_id

    def test_fuel_entry_notes_optional(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user, group, vehicle = self._setup(
            db, create_test_user, create_test_group, create_test_vehicle
        )
        entry_no_notes = FuelEntry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=20.0,
            usage_reading=100.0,
            entry_date=date(2025, 1, 1),
        )
        db.add(entry_no_notes)
        db.commit()
        assert entry_no_notes.notes is None

        entry_with_notes = FuelEntry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=25.0,
            usage_reading=200.0,
            entry_date=date(2025, 1, 2),
            notes="Filled at local station",
        )
        db.add(entry_with_notes)
        db.commit()
        assert entry_with_notes.notes == "Filled at local station"

    def test_fuel_entry_soft_delete(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user, group, vehicle = self._setup(
            db, create_test_user, create_test_group, create_test_vehicle
        )
        entry = FuelEntry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=800.0,
            entry_date=date(2025, 3, 1),
        )
        db.add(entry)
        db.commit()

        entry.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(entry)
        assert entry.deleted_at is not None


# ── AuditLog ─────────────────────────────────────────────────────────────────


class TestAuditLog:
    def test_create_audit_log_valid(
        self, db, create_test_user, create_test_group
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)

        log = AuditLog(
            group_id=group.id,
            user_id=user.id,
            action="vehicle.create",
            entity_type="vehicle",
            entity_id=1,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        assert log.id is not None
        assert log.action == "vehicle.create"
        assert log.entity_type == "vehicle"
        assert log.entity_id == 1
        assert log.created_at is not None


# ── Relationships ────────────────────────────────────────────────────────────


class TestRelationships:
    def test_user_has_many_groups_through_user_group(
        self, db, create_test_user, create_test_group
    ):
        user = create_test_user()
        g1 = create_test_group(name="Farm A", invite_code="FARM-AAAA1", created_by=user.id)
        g2 = create_test_group(name="Farm B", invite_code="FARM-BBBB1", created_by=user.id)

        db.add(UserGroup(user_id=user.id, group_id=g1.id, role="admin"))
        db.add(UserGroup(user_id=user.id, group_id=g2.id, role="contributor"))
        db.commit()
        db.refresh(user)

        group_ids = {ug.group_id for ug in user.user_groups}
        assert g1.id in group_ids
        assert g2.id in group_ids

    def test_group_has_many_users_through_user_group(
        self, db, create_test_group
    ):
        u1 = User(email="u1@farm.com", name="U1", password_hash="h")
        u2 = User(email="u2@farm.com", name="U2", password_hash="h")
        db.add_all([u1, u2])
        db.commit()

        group = create_test_group(created_by=u1.id)
        db.add(UserGroup(user_id=u1.id, group_id=group.id, role="admin"))
        db.add(UserGroup(user_id=u2.id, group_id=group.id, role="reader"))
        db.commit()
        db.refresh(group)

        user_ids = {ug.user_id for ug in group.user_groups}
        assert u1.id in user_ids
        assert u2.id in user_ids

    def test_group_has_many_vehicles(
        self, db, create_test_user, create_test_group
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)

        v1 = Vehicle(group_id=group.id, name="V1", vtype="car", fuel_type="petrol")
        v2 = Vehicle(group_id=group.id, name="V2", vtype="tractor", fuel_type="diesel")
        db.add_all([v1, v2])
        db.commit()
        db.refresh(group)

        assert len(group.vehicles) == 2

    def test_vehicle_has_many_fuel_entries(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)

        e1 = FuelEntry(
            vehicle_id=vehicle.id, group_id=group.id, user_id=user.id,
            fuel_amount_l=30.0, usage_reading=100.0, entry_date=date(2025, 1, 1),
        )
        e2 = FuelEntry(
            vehicle_id=vehicle.id, group_id=group.id, user_id=user.id,
            fuel_amount_l=35.0, usage_reading=200.0, entry_date=date(2025, 2, 1),
        )
        db.add_all([e1, e2])
        db.commit()
        db.refresh(vehicle)

        assert len(vehicle.fuel_entries) == 2

    def test_fuel_entry_belongs_to_user(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)

        entry = FuelEntry(
            vehicle_id=vehicle.id, group_id=group.id, user_id=user.id,
            fuel_amount_l=40.0, usage_reading=300.0, entry_date=date(2025, 3, 1),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        assert entry.user.id == user.id
        assert entry.user.name == user.name
