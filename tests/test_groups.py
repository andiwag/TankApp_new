"""Tests for Phase 5: Group System."""

from datetime import datetime, timezone

import pytest

from app.auth import decode_session_cookie
from app.config import settings
from app.models import Group, UserGroup


# ── Create Group ─────────────────────────────────────────────────────────────


class TestCreateGroup:
    async def test_create_group_valid(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.post("/groups/create", data={"name": "My Farm"})
        assert response.status_code == 303

        group = db.query(Group).filter(Group.name == "My Farm").first()
        assert group is not None
        assert group.created_by == user.id

    async def test_create_group_sets_creator_as_admin(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        await client.post("/groups/create", data={"name": "My Farm"})

        group = db.query(Group).filter(Group.name == "My Farm").first()
        ug = db.query(UserGroup).filter(
            UserGroup.user_id == user.id,
            UserGroup.group_id == group.id,
        ).first()
        assert ug is not None
        assert ug.role == "admin"

    async def test_create_group_generates_invite_code(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        await client.post("/groups/create", data={"name": "My Farm"})

        group = db.query(Group).filter(Group.name == "My Farm").first()
        assert group.invite_code is not None
        assert group.invite_code.startswith("FARM-")
        assert len(group.invite_code) == 10

    async def test_create_group_empty_name_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.post("/groups/create", data={"name": ""})

        assert response.status_code == 200
        assert db.query(Group).count() == 0


# ── Join Group ───────────────────────────────────────────────────────────────


class TestJoinGroup:
    async def test_join_group_valid_code(
        self, client, create_test_user, create_test_group, auth_cookie, db
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(
            name="Existing Farm", invite_code="FARM-JOIN1", created_by=owner.id
        )

        joiner = create_test_user(email="joiner@farm.com", name="Joiner")
        auth_cookie(client, joiner.id)

        response = await client.post(
            "/groups/join", data={"invite_code": "FARM-JOIN1"}
        )
        assert response.status_code == 303

        ug = db.query(UserGroup).filter(
            UserGroup.user_id == joiner.id,
            UserGroup.group_id == group.id,
        ).first()
        assert ug is not None

    async def test_join_group_invalid_code_fails(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.post(
            "/groups/join", data={"invite_code": "INVALID-CODE"}
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "not found" in body

    async def test_join_group_sets_role_contributor(
        self, client, create_test_user, create_test_group, auth_cookie, db
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(
            name="Farm", invite_code="FARM-ROLE1", created_by=owner.id
        )

        joiner = create_test_user(email="joiner@farm.com", name="Joiner")
        auth_cookie(client, joiner.id)
        await client.post("/groups/join", data={"invite_code": "FARM-ROLE1"})

        ug = db.query(UserGroup).filter(
            UserGroup.user_id == joiner.id,
            UserGroup.group_id == group.id,
        ).first()
        assert ug is not None
        assert ug.role == "contributor"

    async def test_join_group_already_member_shows_error(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie,
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(
            name="Farm", invite_code="FARM-MEMB1", created_by=owner.id
        )
        create_test_user_group(owner.id, group.id, "admin")

        auth_cookie(client, owner.id)
        response = await client.post(
            "/groups/join", data={"invite_code": "FARM-MEMB1"}
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "already" in body or "member" in body

    async def test_join_group_deleted_group_fails(
        self, client, create_test_user, create_test_group, auth_cookie, db
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(
            name="Dead Farm", invite_code="FARM-DEAD1", created_by=owner.id
        )
        group.deleted_at = datetime.now(timezone.utc)
        db.commit()

        joiner = create_test_user(email="joiner@farm.com", name="Joiner")
        auth_cookie(client, joiner.id)

        response = await client.post(
            "/groups/join", data={"invite_code": "FARM-DEAD1"}
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "not found" in body


# ── Switch Group ─────────────────────────────────────────────────────────────


class TestSwitchGroup:
    async def test_switch_group_valid(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, "admin")

        auth_cookie(client, user.id)
        response = await client.post(f"/groups/switch/{group.id}")
        assert response.status_code == 303
        assert "/dashboard" in response.headers["location"]

    async def test_switch_group_not_member_fails(
        self, client, create_test_user, create_test_group, auth_cookie
    ):
        user = create_test_user()
        owner = create_test_user(email="owner@farm.com", name="Owner")
        group = create_test_group(created_by=owner.id)

        auth_cookie(client, user.id)
        response = await client.post(f"/groups/switch/{group.id}")
        assert response.status_code == 403

    async def test_switch_group_updates_session(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, "admin")

        auth_cookie(client, user.id)
        response = await client.post(f"/groups/switch/{group.id}")

        assert settings.SESSION_COOKIE_NAME in response.cookies
        cookie_value = response.cookies[settings.SESSION_COOKIE_NAME]
        data = decode_session_cookie(cookie_value)
        assert data is not None
        assert data["active_group_id"] == group.id


# ── Leave Group ──────────────────────────────────────────────────────────────


class TestLeaveGroup:
    async def test_leave_group_as_contributor(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(created_by=owner.id)
        create_test_user_group(owner.id, group.id, "admin")

        contributor = create_test_user(email="contrib@farm.com", name="Contrib")
        create_test_user_group(contributor.id, group.id, "contributor")

        auth_cookie(client, contributor.id, group.id)
        response = await client.post(f"/groups/leave/{group.id}")
        assert response.status_code == 303

        ug = db.query(UserGroup).filter(
            UserGroup.user_id == contributor.id,
            UserGroup.group_id == group.id,
        ).first()
        assert ug is None

    async def test_leave_group_as_admin_with_other_admins(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        admin1 = create_test_user(email="admin1@farm.com")
        group = create_test_group(created_by=admin1.id)
        create_test_user_group(admin1.id, group.id, "admin")

        admin2 = create_test_user(email="admin2@farm.com", name="Admin2")
        create_test_user_group(admin2.id, group.id, "admin")

        auth_cookie(client, admin1.id, group.id)
        response = await client.post(f"/groups/leave/{group.id}")
        assert response.status_code == 303

        ug = db.query(UserGroup).filter(
            UserGroup.user_id == admin1.id,
            UserGroup.group_id == group.id,
        ).first()
        assert ug is None

    async def test_leave_group_as_sole_admin_fails(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, "admin")

        auth_cookie(client, user.id, group.id)
        response = await client.post(f"/groups/leave/{group.id}")

        ug = db.query(UserGroup).filter(
            UserGroup.user_id == user.id,
            UserGroup.group_id == group.id,
        ).first()
        assert ug is not None
        assert response.status_code != 303

    async def test_leave_group_not_member_fails(
        self, client, create_test_user, create_test_group, auth_cookie
    ):
        user = create_test_user()
        owner = create_test_user(email="owner@farm.com", name="Owner")
        group = create_test_group(created_by=owner.id)

        auth_cookie(client, user.id)
        response = await client.post(f"/groups/leave/{group.id}")
        assert response.status_code == 403


# ── Delete Group ─────────────────────────────────────────────────────────────


class TestDeleteGroup:
    async def test_delete_group_as_admin(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, "admin")

        auth_cookie(client, user.id, group.id)
        response = await client.post(f"/groups/delete/{group.id}")
        assert response.status_code == 303

        db.refresh(group)
        assert group.deleted_at is not None

    async def test_delete_group_as_contributor_fails(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(created_by=owner.id)

        contributor = create_test_user(email="contrib@farm.com", name="Contrib")
        create_test_user_group(contributor.id, group.id, "contributor")

        auth_cookie(client, contributor.id, group.id)
        response = await client.post(f"/groups/delete/{group.id}")
        assert response.status_code == 403

    async def test_delete_group_as_reader_fails(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(created_by=owner.id)

        reader = create_test_user(email="reader@farm.com", name="Reader")
        create_test_user_group(reader.id, group.id, "reader")

        auth_cookie(client, reader.id, group.id)
        response = await client.post(f"/groups/delete/{group.id}")
        assert response.status_code == 403

    async def test_delete_group_soft_deletes(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, "admin")

        auth_cookie(client, user.id, group.id)
        await client.post(f"/groups/delete/{group.id}")

        db.refresh(group)
        assert group.deleted_at is not None
        assert db.query(Group).filter(Group.id == group.id).first() is not None


# ── Authorization ────────────────────────────────────────────────────────────


class TestGroupAuthorization:
    async def test_group_routes_require_authentication(self, client):
        response = await client.get("/groups")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    async def test_create_group_any_authenticated_user(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.post("/groups/create", data={"name": "My Farm"})
        assert response.status_code == 303
        assert db.query(Group).filter(Group.name == "My Farm").first() is not None

    async def test_delete_group_requires_admin(
        self, client, create_test_user, create_test_group,
        create_test_user_group, auth_cookie, db,
    ):
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(created_by=owner.id)

        contributor = create_test_user(email="contrib@farm.com", name="Contrib")
        create_test_user_group(contributor.id, group.id, "contributor")

        auth_cookie(client, contributor.id, group.id)
        response = await client.post(f"/groups/delete/{group.id}")
        assert response.status_code == 403

        db.refresh(group)
        assert group.deleted_at is None
