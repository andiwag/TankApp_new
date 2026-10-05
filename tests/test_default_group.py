"""Default farm selection when a session has no active group."""

from datetime import timedelta

from app.auth import decode_session_cookie
from app.config import settings
from app.time_utils import utc_now


def _active_group_id(client, response) -> int | None:
    prefix = f"{settings.SESSION_COOKIE_NAME}="
    cookie_value = None
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(prefix):
            cookie_value = header.split(";", 1)[0][len(prefix) :]
            break
    if cookie_value is None:
        values = [
            cookie.value
            for cookie in client.cookies.jar
            if cookie.name == settings.SESSION_COOKIE_NAME
        ]
        cookie_value = values[-1] if values else None
    if not cookie_value:
        return None
    data = decode_session_cookie(cookie_value)
    if not data:
        return None
    return data.get("active_group_id")


class TestDefaultGroup:
    async def test_sole_farm_opens_dashboard_without_switch(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(
            name="Only Farm", invite_code="FARM-ONLY1", created_by=user.id
        )
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Only Farm" in response.text
        assert _active_group_id(client, response) == group.id

    async def test_user_with_no_farm_still_reaches_group_list(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"

    async def test_group_list_stays_available_when_a_default_exists(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(
            name="Listed Farm", invite_code="FARM-LIST1", created_by=user.id
        )
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id)

        response = await client.get("/groups", follow_redirects=False)

        assert response.status_code == 200
        assert "Listed Farm" in response.text
        assert "Aktiv" in response.text

    async def test_earliest_membership_opens_when_none_was_saved(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        later = create_test_group(
            name="Later Farm", invite_code="FARM-LATR1", created_by=user.id
        )
        earlier = create_test_group(
            name="Earlier Farm", invite_code="FARM-ERLY1", created_by=user.id
        )
        later_membership = create_test_user_group(user.id, later.id, role="admin")
        earlier_membership = create_test_user_group(user.id, earlier.id, role="admin")
        later_membership.joined_at = utc_now() - timedelta(days=1)
        earlier_membership.joined_at = utc_now() - timedelta(days=30)
        db.commit()
        auth_cookie(client, user.id)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Earlier Farm" in response.text
        assert _active_group_id(client, response) == earlier.id

    async def test_equal_join_times_open_the_lowest_group_id(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        first = create_test_group(
            name="First Id Farm", invite_code="FARM-ID001", created_by=user.id
        )
        second = create_test_group(
            name="Second Id Farm", invite_code="FARM-ID002", created_by=user.id
        )
        first_membership = create_test_user_group(user.id, first.id, role="admin")
        second_membership = create_test_user_group(user.id, second.id, role="admin")
        stamp = utc_now() - timedelta(days=3)
        first_membership.joined_at = stamp
        second_membership.joined_at = stamp
        db.commit()
        auth_cookie(client, user.id)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert _active_group_id(client, response) == first.id

    async def test_switch_becomes_the_farm_opened_next_time(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        first = create_test_group(
            name="First Farm", invite_code="FARM-SW001", created_by=user.id
        )
        second = create_test_group(
            name="Second Farm", invite_code="FARM-SW002", created_by=user.id
        )
        create_test_user_group(user.id, first.id, role="admin")
        create_test_user_group(user.id, second.id, role="admin")
        auth_cookie(client, user.id, first.id)
        await client.post(f"/groups/switch/{second.id}", follow_redirects=False)

        auth_cookie(client, user.id)
        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Second Farm" in response.text
        assert _active_group_id(client, response) == second.id

    async def test_selected_cookie_wins_over_saved_default(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        first = create_test_group(
            name="Cookie Farm", invite_code="FARM-CK001", created_by=user.id
        )
        second = create_test_group(
            name="Saved Farm", invite_code="FARM-CK002", created_by=user.id
        )
        create_test_user_group(user.id, first.id, role="admin")
        create_test_user_group(user.id, second.id, role="admin")
        auth_cookie(client, user.id, second.id)
        await client.get("/dashboard")

        auth_cookie(client, user.id, first.id)
        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Cookie Farm" in response.text
        assert _active_group_id(client, response) == first.id

        auth_cookie(client, user.id)
        restored = await client.get("/dashboard", follow_redirects=False)
        assert restored.status_code == 200
        assert _active_group_id(client, restored) == first.id

    async def test_deleted_farm_in_cookie_falls_back_to_a_live_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        deleted = create_test_group(
            name="Deleted Farm", invite_code="FARM-DEL01", created_by=user.id
        )
        live = create_test_group(
            name="Live Farm", invite_code="FARM-LIV01", created_by=user.id
        )
        create_test_user_group(user.id, deleted.id, role="admin")
        create_test_user_group(user.id, live.id, role="admin")
        deleted.deleted_at = utc_now()
        db.commit()
        auth_cookie(client, user.id, deleted.id)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Live Farm" in response.text
        assert _active_group_id(client, response) == live.id

    async def test_deleted_only_farm_returns_to_group_list(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        group = create_test_group(
            name="Gone Farm", invite_code="FARM-GONE1", created_by=user.id
        )
        create_test_user_group(user.id, group.id, role="admin")
        group.deleted_at = utc_now()
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"
        assert _active_group_id(client, response) is None

    async def test_removed_member_with_another_farm_opens_that_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        removed = create_test_group(
            name="Removed Farm", invite_code="FARM-REM01", created_by=user.id
        )
        kept = create_test_group(
            name="Kept Farm", invite_code="FARM-KEP01", created_by=user.id
        )
        create_test_user_group(user.id, removed.id, role="contributor")
        create_test_user_group(user.id, kept.id, role="admin")
        auth_cookie(client, user.id, removed.id)
        from app.models import UserGroup

        db.query(UserGroup).filter(
            UserGroup.user_id == user.id,
            UserGroup.group_id == removed.id,
        ).delete()
        db.commit()

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Kept Farm" in response.text
        assert _active_group_id(client, response) == kept.id

    async def test_create_opens_the_new_farm(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.post(
            "/groups/create", data={"name": "Brand New Farm"}, follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"
        assert "Brand New Farm" in (await client.get("/dashboard")).text

    async def test_join_opens_the_joined_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        owner = create_test_user(email="owner-join@farm.com")
        existing = create_test_group(
            name="Home Farm", invite_code="FARM-HOME1", created_by=owner.id
        )
        joined = create_test_group(
            name="Joined Farm", invite_code="FARM-JOIN2", created_by=owner.id
        )
        create_test_user_group(owner.id, existing.id, role="admin")
        create_test_user_group(owner.id, joined.id, role="admin")
        joiner = create_test_user(email="joiner-default@farm.com")
        create_test_user_group(joiner.id, existing.id, role="contributor")
        auth_cookie(client, joiner.id, existing.id)

        response = await client.post(
            "/groups/join", data={"invite_code": "FARM-JOIN2"}, follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"
        assert _active_group_id(client, response) == joined.id

    async def test_leave_open_farm_opens_the_remaining_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        staying = create_test_group(
            name="Staying Farm", invite_code="FARM-STAY1", created_by=user.id
        )
        leaving = create_test_group(
            name="Leaving Farm", invite_code="FARM-LEAV1", created_by=user.id
        )
        create_test_user_group(user.id, staying.id, role="contributor")
        create_test_user_group(user.id, leaving.id, role="contributor")
        owner = create_test_user(email="owner-leave@farm.com")
        create_test_user_group(owner.id, staying.id, role="admin")
        create_test_user_group(owner.id, leaving.id, role="admin")
        auth_cookie(client, user.id, leaving.id)

        response = await client.post(
            f"/groups/leave/{leaving.id}", follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"
        assert _active_group_id(client, response) == staying.id

    async def test_leave_last_farm_returns_to_group_list(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        owner = create_test_user(email="owner-last@farm.com")
        group = create_test_group(
            name="Last Farm", invite_code="FARM-LAST1", created_by=owner.id
        )
        create_test_user_group(owner.id, group.id, role="admin")
        member = create_test_user(email="member-last@farm.com")
        create_test_user_group(member.id, group.id, role="contributor")
        auth_cookie(client, member.id, group.id)

        response = await client.post(
            f"/groups/leave/{group.id}", follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"
        assert _active_group_id(client, response) is None

    async def test_delete_open_farm_opens_the_remaining_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        staying = create_test_group(
            name="Keep Farm", invite_code="FARM-KEEP1", created_by=user.id
        )
        closing = create_test_group(
            name="Close Farm", invite_code="FARM-CLOS1", created_by=user.id
        )
        create_test_user_group(user.id, staying.id, role="admin")
        create_test_user_group(user.id, closing.id, role="admin")
        auth_cookie(client, user.id, closing.id)

        response = await client.post(
            f"/groups/delete/{closing.id}", follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"
        assert _active_group_id(client, response) == staying.id

    async def test_landing_with_one_farm_opens_dashboard(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(
            name="Landing Farm", invite_code="FARM-LAND1", created_by=user.id
        )
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id)

        response = await client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"

    async def test_platform_view_does_not_replace_the_saved_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "app.config.settings.PLATFORM_ADMIN_EMAILS", "ops-default@tankly.test"
        )
        operator = create_test_user(email="ops-default@tankly.test", name="Operator")
        own = create_test_group(
            name="Own Farm", invite_code="FARM-OWN01", created_by=operator.id
        )
        customer = create_test_group(
            name="Customer Farm", invite_code="FARM-CUST1", created_by=operator.id
        )
        create_test_user_group(operator.id, own.id, role="admin")
        create_test_user_group(operator.id, customer.id, role="contributor")
        auth_cookie(client, operator.id, own.id)
        await client.get("/dashboard")
        await client.post(f"/platform/farms/{customer.id}/enter")
        await client.post("/platform/exit-view", follow_redirects=False)

        response = await client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 200
        assert "Own Farm" in response.text
        assert "Customer Farm" not in response.text
        assert _active_group_id(client, response) == own.id
