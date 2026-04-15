"""Tests for Phase 8: Vehicles CRUD."""

from datetime import datetime, timezone

import pytest

from app.models import Vehicle


def _auth_group(
    client,
    create_test_user,
    create_test_group,
    create_test_user_group,
    auth_cookie,
    *,
    role: str = "admin",
):
    user = create_test_user()
    group = create_test_group(created_by=user.id)
    create_test_user_group(user.id, group.id, role=role)
    auth_cookie(client, user.id, group.id)
    return user, group


class TestListVehicles:
    @pytest.mark.asyncio
    async def test_list_vehicles_requires_auth(self, client):
        response = await client.get("/vehicles", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    @pytest.mark.asyncio
    async def test_list_vehicles_returns_200(
        self, client, create_test_user, create_test_group, create_test_user_group, auth_cookie
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        response = await client.get("/vehicles")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_vehicles_scoped_to_active_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(name="Farm A", invite_code="FARM-AAAAA", created_by=user.id)
        g_b = create_test_group(name="Farm B", invite_code="FARM-BBBBB", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="admin")
        create_test_user_group(user.id, g_b.id, role="admin")
        create_test_vehicle(group_id=g_a.id, name="Only A")
        create_test_vehicle(group_id=g_b.id, name="Only B")
        auth_cookie(client, user.id, g_a.id)
        response = await client.get("/vehicles")
        assert response.status_code == 200
        assert "Only A" in response.text
        assert "Only B" not in response.text

    @pytest.mark.asyncio
    async def test_list_vehicles_excludes_soft_deleted(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        create_test_vehicle(group_id=group.id, name="Visible")
        v_del = create_test_vehicle(group_id=group.id, name="Hidden")
        db.query(Vehicle).filter(Vehicle.id == v_del.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()

        response = await client.get("/vehicles")
        assert response.status_code == 200
        assert "Visible" in response.text
        assert "Hidden" not in response.text


class TestCreateVehicle:
    @pytest.mark.asyncio
    async def test_create_vehicle_valid_car(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.post(
            "/vehicles/new",
            data={"name": "Family Car", "vtype": "car", "fuel_type": "petrol"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/vehicles"
        v = db.query(Vehicle).filter(Vehicle.name == "Family Car").one()
        assert v.group_id == group.id
        assert v.vtype == "car"
        assert v.usage_unit == "km"
        assert v.fuel_type == "petrol"

    @pytest.mark.asyncio
    async def test_create_vehicle_valid_tractor(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
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
            follow_redirects=False,
        )
        assert response.status_code == 303
        v = db.query(Vehicle).filter(Vehicle.name == "Big Tractor").one()
        assert v.group_id == group.id
        assert v.vtype == "tractor"
        assert v.usage_unit == "hours"

    @pytest.mark.asyncio
    async def test_create_vehicle_sets_usage_unit_km_for_car(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        await client.post(
            "/vehicles/new",
            data={"name": "C1", "vtype": "car", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        v = db.query(Vehicle).filter(Vehicle.name == "C1").one()
        assert v.usage_unit == "km"

    @pytest.mark.asyncio
    async def test_create_vehicle_sets_usage_unit_km_for_motorcycle(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        await client.post(
            "/vehicles/new",
            data={"name": "M1", "vtype": "motorcycle", "fuel_type": "petrol"},
            follow_redirects=False,
        )
        v = db.query(Vehicle).filter(Vehicle.name == "M1").one()
        assert v.usage_unit == "km"

    @pytest.mark.asyncio
    async def test_create_vehicle_sets_usage_unit_hours_for_tractor(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        await client.post(
            "/vehicles/new",
            data={"name": "T1", "vtype": "tractor", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        v = db.query(Vehicle).filter(Vehicle.name == "T1").one()
        assert v.usage_unit == "hours"

    @pytest.mark.asyncio
    async def test_create_vehicle_sets_usage_unit_hours_for_machine(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        await client.post(
            "/vehicles/new",
            data={"name": "Mach1", "vtype": "machine", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        v = db.query(Vehicle).filter(Vehicle.name == "Mach1").one()
        assert v.usage_unit == "hours"

    @pytest.mark.asyncio
    async def test_create_vehicle_sets_group_id_from_session(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        await client.post(
            "/vehicles/new",
            data={"name": "Scoped", "vtype": "car", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        v = db.query(Vehicle).filter(Vehicle.name == "Scoped").one()
        assert v.group_id == group.id

    @pytest.mark.asyncio
    async def test_create_vehicle_invalid_vtype_fails(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.post(
            "/vehicles/new",
            data={"name": "Bad", "vtype": "not_a_type", "fuel_type": "diesel"},
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text
        assert "Input should" in response.text

    @pytest.mark.asyncio
    async def test_create_vehicle_empty_name_fails(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.post(
            "/vehicles/new",
            data={"name": "   ", "vtype": "car", "fuel_type": "diesel"},
        )
        assert response.status_code == 200
        assert "empty" in response.text.lower() or "Name" in response.text

    @pytest.mark.asyncio
    async def test_create_vehicle_requires_contributor_role(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        r_get = await client.get("/vehicles/new", follow_redirects=False)
        assert r_get.status_code == 403
        r_post = await client.post(
            "/vehicles/new",
            data={"name": "Nope", "vtype": "car", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert r_post.status_code == 403

    @pytest.mark.asyncio
    async def test_create_vehicle_reader_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        response = await client.post(
            "/vehicles/new",
            data={"name": "Nope", "vtype": "car", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert response.status_code == 403


class TestEditVehicle:
    @pytest.mark.asyncio
    async def test_edit_vehicle_valid(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id, name="Old", vtype="tractor", fuel_type="diesel")
        response = await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "New Name", "fuel_type": "petrol"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(v)
        assert v.name == "New Name"
        assert v.fuel_type == "petrol"
        assert v.vtype == "tractor"
        assert v.usage_unit == "hours"

    @pytest.mark.asyncio
    async def test_edit_vehicle_name_only(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id, name="Old", vtype="car", fuel_type="diesel")
        await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "Renamed", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        db.refresh(v)
        assert v.name == "Renamed"
        assert v.fuel_type == "diesel"

    @pytest.mark.asyncio
    async def test_edit_vehicle_fuel_type_only(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id, name="Same", vtype="car", fuel_type="diesel")
        await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "Same", "fuel_type": "petrol"},
            follow_redirects=False,
        )
        db.refresh(v)
        assert v.name == "Same"
        assert v.fuel_type == "petrol"

    @pytest.mark.asyncio
    async def test_edit_vehicle_partial_update(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id, name="V", vtype="tractor", fuel_type="diesel")
        await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "V2", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        db.refresh(v)
        assert v.name == "V2"
        assert v.fuel_type == "diesel"

    @pytest.mark.asyncio
    async def test_edit_vehicle_wrong_group_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAAAA", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBBBB", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="contributor")
        create_test_user_group(user.id, g_b.id, role="contributor")
        v_in_b = create_test_vehicle(group_id=g_b.id, name="Other")
        auth_cookie(client, user.id, g_a.id)
        response = await client.post(
            f"/vehicles/{v_in_b.id}/edit",
            data={"name": "Hack", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_vehicle_requires_contributor_role(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        v = create_test_vehicle(group_id=group.id)
        r_get = await client.get(f"/vehicles/{v.id}/edit", follow_redirects=False)
        assert r_get.status_code == 403
        r_post = await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "X", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert r_post.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_vehicle_reader_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        v = create_test_vehicle(group_id=group.id)
        response = await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "X", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_vehicle_not_found_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        response = await client.post(
            "/vehicles/99999/edit",
            data={"name": "X", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_soft_deleted_vehicle_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id)
        db.query(Vehicle).filter(Vehicle.id == v.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()
        response = await client.post(
            f"/vehicles/{v.id}/edit",
            data={"name": "X", "fuel_type": "diesel"},
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestDeleteVehicle:
    @pytest.mark.asyncio
    async def test_delete_vehicle_as_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        v = create_test_vehicle(group_id=group.id)
        response = await client.post(f"/vehicles/{v.id}/delete", follow_redirects=False)
        assert response.status_code == 303
        db.refresh(v)
        assert v.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_vehicle_as_contributor_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id)
        response = await client.post(f"/vehicles/{v.id}/delete", follow_redirects=False)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_vehicle_as_reader_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        v = create_test_vehicle(group_id=group.id)
        response = await client.post(f"/vehicles/{v.id}/delete", follow_redirects=False)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_vehicle_sets_deleted_at(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        v = create_test_vehicle(group_id=group.id)
        assert v.deleted_at is None
        await client.post(f"/vehicles/{v.id}/delete", follow_redirects=False)
        db.refresh(v)
        assert v.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_vehicle_wrong_group_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAAAA", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBBBB", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="admin")
        create_test_user_group(user.id, g_b.id, role="admin")
        v_in_b = create_test_vehicle(group_id=g_b.id)
        auth_cookie(client, user.id, g_a.id)
        response = await client.post(f"/vehicles/{v_in_b.id}/delete", follow_redirects=False)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_vehicle_not_found_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        response = await client.post("/vehicles/99999/delete", follow_redirects=False)
        assert response.status_code == 404


class TestGroupRoutesAuth:
    @pytest.mark.asyncio
    async def test_group_routes_require_authentication(
        self, client, create_test_user, create_test_group, create_test_user_group, auth_cookie
    ):
        response = await client.get("/vehicles", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    @pytest.mark.asyncio
    async def test_create_group_any_authenticated_user(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        """Plan name: any authenticated user may access group-scoped list (vehicles list)."""
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="reader",
        )
        response = await client.get("/vehicles")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_group_requires_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        """Vehicle delete requires admin (mirrors plan's delete_group_requires_admin pattern)."""
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        v = create_test_vehicle(group_id=group.id)
        response = await client.post(f"/vehicles/{v.id}/delete", follow_redirects=False)
        assert response.status_code == 403
