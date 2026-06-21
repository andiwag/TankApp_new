"""Tests for Phase 13: Audit Logging."""

from datetime import date

from app.models import AuditLog, FuelEntry, User, Vehicle

from tests.conftest import create_authenticated_group


def _audit_log(db, action: str) -> AuditLog:
    return db.query(AuditLog).filter(AuditLog.action == action).one()


def _audit_count(db) -> int:
    return db.query(AuditLog).count()


class TestAuditLoggedEvents:
    async def test_audit_log_created_on_user_register(self, client, db):
        response = await client.post(
            "/register",
            data={
                "name": "Alice",
                "email": "alice@farm.com",
                "password": "secret1234",
                "password_confirm": "secret1234",
            },
        )
        assert response.status_code == 303

        user = db.query(User).filter(User.email == "alice@farm.com").one()
        log = _audit_log(db, "user.register")
        assert log.group_id is None
        assert log.user_id == user.id
        assert log.entity_type == "user"
        assert log.entity_id == user.id

    async def test_audit_log_created_on_group_create(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.post("/groups/create", data={"name": "My Farm"})
        assert response.status_code == 303

        log = _audit_log(db, "group.create")
        assert log.group_id == log.entity_id
        assert log.user_id == user.id
        assert log.entity_type == "group"

    async def test_audit_log_created_on_group_delete(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )

        response = await client.post(f"/groups/delete/{group.id}")
        assert response.status_code == 303

        log = _audit_log(db, "group.delete")
        assert log.group_id == group.id
        assert log.user_id == user.id
        assert log.entity_type == "group"
        assert log.entity_id == group.id

    async def test_audit_log_created_on_group_join(
        self, client, create_test_user, create_test_group, auth_cookie, db
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(
            name="Existing Farm", invite_code="FARM-JOIN1", created_by=owner.id
        )
        joiner = create_test_user(email="joiner@farm.com", name="Joiner")
        auth_cookie(client, joiner.id)

        response = await client.post("/groups/join", data={"invite_code": "FARM-JOIN1"})
        assert response.status_code == 303

        log = _audit_log(db, "group.join")
        assert log.group_id == group.id
        assert log.user_id == joiner.id
        assert log.entity_type == "group"
        assert log.entity_id == group.id

    async def test_audit_log_created_on_group_leave(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(created_by=owner.id)
        create_test_user_group(owner.id, group.id, "admin")
        contributor = create_test_user(email="contrib@farm.com", name="Contrib")
        create_test_user_group(contributor.id, group.id, "contributor")
        auth_cookie(client, contributor.id, group.id)

        response = await client.post(f"/groups/leave/{group.id}")
        assert response.status_code == 303

        log = _audit_log(db, "group.leave")
        assert log.group_id == group.id
        assert log.user_id == contributor.id
        assert log.entity_type == "group"
        assert log.entity_id == group.id

    async def test_audit_log_created_on_member_role_change(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        admin, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        member = create_test_user(email="member@example.com", name="Member")
        create_test_user_group(member.id, group.id, role="reader")

        response = await client.post(
            f"/settings/group/members/{member.id}/role",
            data={"role": "contributor"},
        )
        assert response.status_code == 303

        log = _audit_log(db, "member.role_change")
        assert log.group_id == group.id
        assert log.user_id == admin.id
        assert log.entity_type == "user_group"
        assert log.entity_id == member.id

    async def test_audit_log_created_on_member_remove(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        admin, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        member = create_test_user(email="member@example.com", name="Member")
        create_test_user_group(member.id, group.id, role="contributor")

        response = await client.post(f"/settings/group/members/{member.id}/remove")
        assert response.status_code == 303

        log = _audit_log(db, "member.remove")
        assert log.group_id == group.id
        assert log.user_id == admin.id
        assert log.entity_type == "user_group"
        assert log.entity_id == member.id

    async def test_audit_log_created_on_vehicle_create(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
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

        response = await client.post(
            "/vehicles/new",
            data={"name": "Big Tractor", "vtype": "tractor", "fuel_type": "diesel"},
        )
        assert response.status_code == 303

        vehicle = db.query(Vehicle).filter(Vehicle.name == "Big Tractor").one()
        log = _audit_log(db, "vehicle.create")
        assert log.group_id == group.id
        assert log.user_id == user.id
        assert log.entity_type == "vehicle"
        assert log.entity_id == vehicle.id

    async def test_audit_log_created_on_vehicle_delete(
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
        )
        vehicle = create_test_vehicle(group_id=group.id, name="Old Tractor")

        response = await client.post(f"/vehicles/{vehicle.id}/delete")
        assert response.status_code == 303

        log = _audit_log(db, "vehicle.delete")
        assert log.group_id == group.id
        assert log.user_id == user.id
        assert log.entity_type == "vehicle"
        assert log.entity_id == vehicle.id


class TestAuditSkippedEvents:
    async def test_audit_log_not_created_on_fuel_entry_create(
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

        before = _audit_count(db)
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(vehicle.id),
                "fuel_amount_l": "50",
                "usage_reading": "100",
                "entry_date": date.today().isoformat(),
                "notes": "",
            },
        )
        assert response.status_code == 303
        assert db.query(FuelEntry).count() == 1
        assert _audit_count(db) == before

    async def test_audit_log_not_created_on_vehicle_edit(
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
        vehicle = create_test_vehicle(group_id=group.id, name="Original")

        before = _audit_count(db)
        response = await client.post(
            f"/vehicles/{vehicle.id}/edit",
            data={"name": "Updated", "fuel_type": "diesel"},
        )
        assert response.status_code == 303
        assert _audit_count(db) == before


class TestAuditMetadata:
    async def test_audit_log_stores_correct_entity_type_and_id(
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
        )
        vehicle = create_test_vehicle(group_id=group.id, name="Tracked Tractor")

        await client.post(f"/vehicles/{vehicle.id}/delete")

        log = _audit_log(db, "vehicle.delete")
        assert log.entity_type == "vehicle"
        assert log.entity_id == vehicle.id

    async def test_audit_log_stores_correct_user_id(
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
        )
        vehicle = create_test_vehicle(group_id=group.id, name="Tracked Tractor")

        await client.post(f"/vehicles/{vehicle.id}/delete")

        log = _audit_log(db, "vehicle.delete")
        assert log.user_id == user.id
