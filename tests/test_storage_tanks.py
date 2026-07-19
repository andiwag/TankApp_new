"""Tests for Phase 25: storage tank CRUD."""

from datetime import date

from app.models import StorageTank
from app.time_utils import utc_now

from tests.conftest import create_authenticated_group


class TestStorageTankCrud:
    async def test_storage_tank_create_diesel(
        self,
        client,
        db,
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
        response = await client.post(
            "/tanks/new",
            data={
                "name": "Diesel Hof",
                "fuel_type": "diesel",
                "opening_balance_l": "500",
                "capacity_l": "5000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        tank = db.query(StorageTank).one()
        assert tank.name == "Diesel Hof"
        assert tank.fuel_type == "diesel"
        assert tank.opening_balance_l == 500.0
        assert tank.capacity_l == 5000.0

    async def test_storage_tank_create_second_petrol_tank_same_group_allowed(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        create_test_storage_tank(group_id=group.id, name="Benzin A", fuel_type="petrol")
        response = await client.post(
            "/tanks/new",
            data={
                "name": "Benzin B",
                "fuel_type": "petrol",
                "opening_balance_l": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert (
            db.query(StorageTank).filter(StorageTank.group_id == group.id).count() == 2
        )

    async def test_storage_tank_list_scoped_to_active_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(
            name="Farm A", invite_code="FARM-AAAAA", created_by=user.id
        )
        g_b = create_test_group(
            name="Farm B", invite_code="FARM-BBBBB", created_by=user.id
        )
        create_test_user_group(user.id, g_a.id, role="admin")
        create_test_user_group(user.id, g_b.id, role="admin")
        create_test_storage_tank(group_id=g_a.id, name="Tank A")
        create_test_storage_tank(group_id=g_b.id, name="Tank B")
        auth_cookie(client, user.id, g_a.id)
        response = await client.get("/tanks")
        assert response.status_code == 200
        assert "Tank A" in response.text
        assert "Tank B" not in response.text

    async def test_storage_tank_detail_404_other_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(
            name="Farm A", invite_code="FARM-AAAAA", created_by=user.id
        )
        g_b = create_test_group(
            name="Farm B", invite_code="FARM-BBBBB", created_by=user.id
        )
        create_test_user_group(user.id, g_a.id, role="admin")
        tank_b = create_test_storage_tank(group_id=g_b.id, name="Secret")
        auth_cookie(client, user.id, g_a.id)
        response = await client.get(f"/tanks/{tank_b.id}")
        assert response.status_code == 404

    async def test_storage_tank_soft_delete_hidden_from_list(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        visible = create_test_storage_tank(group_id=group.id, name="Visible")
        hidden = create_test_storage_tank(group_id=group.id, name="Hidden")
        db.query(StorageTank).filter(StorageTank.id == hidden.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()
        response = await client.get("/tanks")
        assert response.status_code == 200
        assert "Visible" in response.text
        assert "Hidden" not in response.text
        assert visible.id != hidden.id

    async def test_storage_tank_update_name_and_capacity(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tank = create_test_storage_tank(group_id=group.id, name="Old Name")
        response = await client.post(
            f"/tanks/{tank.id}/edit",
            data={
                "name": "New Name",
                "capacity_l": "3000",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(tank)
        assert tank.name == "New Name"
        assert tank.capacity_l == 3000.0

    async def test_storage_tank_delete_requires_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        tank = create_test_storage_tank(group_id=group.id)
        auth_cookie(client, user.id, group.id)
        response = await client.post(
            f"/tanks/{tank.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_storage_tank_reader_can_view_not_create(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="reader")
        create_test_storage_tank(group_id=group.id, name="Reader Tank")
        auth_cookie(client, user.id, group.id)
        assert (await client.get("/tanks")).status_code == 200
        assert (
            await client.get("/tanks/new", follow_redirects=False)
        ).status_code == 403
        assert (
            await client.post(
                "/tanks/new",
                data={"name": "X", "fuel_type": "diesel", "opening_balance_l": "0"},
                follow_redirects=False,
            )
        ).status_code == 403


class TestStorageTankMobile:
    async def test_tanks_page_has_mobile_header_with_add_action(
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
        response = await client.get("/tanks")
        assert response.status_code == 200
        assert "Tanklager" in response.text
        assert 'aria-label="Hinzufügen"' in response.text
        assert 'href="/tanks/new"' in response.text

    async def test_tank_detail_has_mobile_back_and_scrollable_table(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tank = create_test_storage_tank(group_id=group.id, name="Mobile Tank")
        await client.post(
            f"/tanks/{tank.id}/delivery/new",
            data={
                "amount_l": "100",
                "entry_date": date.today().isoformat(),
            },
            follow_redirects=False,
        )
        response = await client.get(f"/tanks/{tank.id}")
        assert response.status_code == 200
        assert 'href="/tanks"' in response.text
        assert 'aria-label="Zurück"' in response.text
        assert "t-table-scroll" in response.text

    async def test_tank_form_has_mobile_back_link(
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
        response = await client.get("/tanks/new")
        assert response.status_code == 200
        assert 'href="/tanks"' in response.text
        assert "sticky bottom-24" in response.text

    async def test_fuel_list_shows_farm_fill_source_badge(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
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
        vehicle = create_test_vehicle(group_id=group.id, name="Farm Tractor")
        tank = create_test_storage_tank(group_id=group.id, name="Diesel Hof")
        entry = create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=500.0,
        )
        entry.fill_source = "farm"
        entry.fuel_tank_id = tank.id
        db.commit()
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "Eigene Tankstelle" in response.text
