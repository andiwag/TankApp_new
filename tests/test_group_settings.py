"""Tests for Phase 12: Group Settings."""

from app.models import Group, UserGroup

from tests.conftest import create_authenticated_group


class TestGroupSettingsPage:
    async def test_group_settings_page_returns_200(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        response = await client.get("/settings/group")
        assert response.status_code == 200

    async def test_group_settings_requires_auth(self, client):
        response = await client.get("/settings/group", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    async def test_group_settings_shows_invite_code(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert "FARM-TEST1" in response.text

    async def test_group_settings_shows_members_with_roles(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        admin = create_test_user(name="Admin Farmer")
        group = create_test_group(created_by=admin.id)
        create_test_user_group(admin.id, group.id, role="admin")
        contributor = create_test_user(
            email="contrib@example.com", name="Contrib Farmer"
        )
        create_test_user_group(contributor.id, group.id, role="contributor")
        auth_cookie(client, admin.id, group.id)

        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert "Admin Farmer" in response.text
        assert "Contrib Farmer" in response.text
        assert 'data-member-role="admin"' in response.text
        assert 'data-member-role="contributor"' in response.text

    async def test_group_settings_admin_sees_role_controls(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        member = create_test_user(email="member@example.com", name="Member")
        create_test_user_group(member.id, group.id, role="reader")
        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert 'data-testid="member-role-form"' in response.text

    async def test_group_settings_contributor_cannot_see_role_controls(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert 'data-testid="member-role-form"' not in response.text
        assert 'data-testid="member-remove-form"' not in response.text

    async def test_group_settings_reader_cannot_see_role_controls(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert 'data-testid="member-role-form"' not in response.text
        assert 'data-testid="member-remove-form"' not in response.text


class TestRegenerateInviteCode:
    async def test_regenerate_invite_code_as_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        response = await client.post("/settings/group/regenerate-code")
        assert response.status_code == 303
        assert response.headers.get("location") == "/settings/group"

    async def test_regenerate_invite_code_as_contributor_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.post("/settings/group/regenerate-code")
        assert response.status_code == 403

    async def test_regenerate_invite_code_changes_code(
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
        old_code = group.invite_code

        await client.post("/settings/group/regenerate-code")

        db.expire_all()
        updated = db.query(Group).filter(Group.id == group.id).one()
        assert updated.invite_code != old_code
        assert updated.invite_code.startswith("FARM-")


class TestChangeMemberRole:
    async def test_change_member_role_as_admin(
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
        db.expire_all()
        ug = (
            db.query(UserGroup)
            .filter(
                UserGroup.user_id == member.id,
                UserGroup.group_id == group.id,
            )
            .one()
        )
        assert ug.role == "contributor"

    async def test_change_member_role_as_contributor_denied(
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
            f"/settings/group/members/{user.id}/role",
            data={"role": "reader"},
        )
        assert response.status_code == 403

    async def test_change_member_role_cannot_demote_self(
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

        response = await client.post(
            f"/settings/group/members/{admin.id}/role",
            data={"role": "contributor"},
        )

        assert response.status_code == 200
        assert "cannot change your own role" in response.text.lower()
        db.expire_all()
        ug = (
            db.query(UserGroup)
            .filter(
                UserGroup.user_id == admin.id,
                UserGroup.group_id == group.id,
            )
            .one()
        )
        assert ug.role == "admin"

    async def test_change_member_role_valid_roles_only(
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
            data={"role": "owner"},
        )

        assert response.status_code == 200
        assert "invalid role" in response.text.lower()
        db.expire_all()
        ug = (
            db.query(UserGroup)
            .filter(
                UserGroup.user_id == member.id,
                UserGroup.group_id == group.id,
            )
            .one()
        )
        assert ug.role == "reader"

    async def test_change_member_role_member_not_in_group_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        admin, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        outsider = create_test_user(email="outsider@example.com", name="Outsider")

        response = await client.post(
            f"/settings/group/members/{outsider.id}/role",
            data={"role": "reader"},
        )
        assert response.status_code == 404


class TestRemoveMember:
    async def test_remove_member_as_admin(
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
        db.expire_all()
        ug = (
            db.query(UserGroup)
            .filter(
                UserGroup.user_id == member.id,
                UserGroup.group_id == group.id,
            )
            .first()
        )
        assert ug is None

    async def test_remove_member_as_contributor_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.post(f"/settings/group/members/{user.id}/remove")
        assert response.status_code == 403

    async def test_remove_member_cannot_remove_self(
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

        response = await client.post(f"/settings/group/members/{admin.id}/remove")

        assert response.status_code == 200
        assert "cannot remove yourself" in response.text.lower()
        db.expire_all()
        ug = (
            db.query(UserGroup)
            .filter(
                UserGroup.user_id == admin.id,
                UserGroup.group_id == group.id,
            )
            .one()
        )
        assert ug.role == "admin"

    async def test_remove_member_not_in_group_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        admin, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        outsider = create_test_user(email="outsider@example.com", name="Outsider")

        response = await client.post(f"/settings/group/members/{outsider.id}/remove")
        assert response.status_code == 404
