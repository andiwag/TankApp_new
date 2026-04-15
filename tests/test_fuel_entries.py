"""Tests for Phase 9: Fuel entries CRUD."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import FuelEntry, Vehicle


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


class TestListFuelEntries:
    @pytest.mark.asyncio
    async def test_list_fuel_entries_requires_auth(self, client):
        response = await client.get("/fuel", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    @pytest.mark.asyncio
    async def test_list_fuel_entries_requires_active_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, None)
        response = await client.get("/fuel", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"

    @pytest.mark.asyncio
    async def test_list_fuel_entries_returns_200(
        self, client, create_test_user, create_test_group, create_test_user_group, auth_cookie
    ):
        _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        response = await client.get("/fuel")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_fuel_entries_scoped_to_active_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(name="Farm A", invite_code="FARM-AAAAA", created_by=user.id)
        g_b = create_test_group(name="Farm B", invite_code="FARM-BBBBB", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="admin")
        create_test_user_group(user.id, g_b.id, role="admin")
        v_a = create_test_vehicle(group_id=g_a.id, name="Tractor A")
        v_b = create_test_vehicle(group_id=g_b.id, name="Tractor B")
        create_test_fuel_entry(
            vehicle_id=v_a.id,
            group_id=g_a.id,
            user_id=user.id,
            fuel_amount_l=10.0,
            usage_reading=1.0,
        )
        create_test_fuel_entry(
            vehicle_id=v_b.id,
            group_id=g_b.id,
            user_id=user.id,
            fuel_amount_l=20.0,
            usage_reading=2.0,
        )
        auth_cookie(client, user.id, g_a.id)
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "Tractor A" in response.text
        assert "Tractor B" not in response.text

    @pytest.mark.asyncio
    async def test_list_fuel_entries_excludes_soft_deleted(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        v = create_test_vehicle(group_id=group.id)
        e_vis = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=5.0,
            usage_reading=10.0,
        )
        e_del = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=876.54,
            usage_reading=11.0,
        )
        db.query(FuelEntry).filter(FuelEntry.id == e_del.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()

        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "5" in response.text or "5.0" in response.text
        assert "876.54" not in response.text

    @pytest.mark.asyncio
    async def test_list_fuel_entries_excludes_entries_for_soft_deleted_vehicle(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        v_ok = create_test_vehicle(group_id=group.id, name="StillHere")
        v_gone = create_test_vehicle(group_id=group.id, name="DeletedVeh")
        create_test_fuel_entry(
            vehicle_id=v_ok.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=11.0,
            usage_reading=1.0,
        )
        create_test_fuel_entry(
            vehicle_id=v_gone.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=333.44,
            usage_reading=2.0,
        )
        db.query(Vehicle).filter(Vehicle.id == v_gone.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()

        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "StillHere" in response.text
        assert "333.44" not in response.text

    @pytest.mark.asyncio
    async def test_list_fuel_entries_shows_vehicle_name(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user, group = _auth_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        v = create_test_vehicle(group_id=group.id, name="UniqueVehicleNameXYZ")
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "UniqueVehicleNameXYZ" in response.text

    @pytest.mark.asyncio
    async def test_list_fuel_entries_shows_user_name(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user(name="FuelLoggerPerson")
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "FuelLoggerPerson" in response.text


class TestCreateFuelEntry:
    @pytest.mark.asyncio
    async def test_create_fuel_entry_valid(
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
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "42.5",
                "usage_reading": "1000",
                "entry_date": d.isoformat(),
                "notes": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/fuel"
        e = db.query(FuelEntry).filter(FuelEntry.vehicle_id == v.id).one()
        assert e.group_id == group.id
        assert e.user_id == user.id
        assert e.fuel_amount_l == 42.5
        assert e.usage_reading == 1000.0
        assert e.entry_date == d
        assert e.notes is None

    @pytest.mark.asyncio
    async def test_create_fuel_entry_sets_group_id_from_vehicle(
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
        d = date.today()
        await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        e = db.query(FuelEntry).one()
        assert e.group_id == v.group_id == group.id

    @pytest.mark.asyncio
    async def test_create_fuel_entry_sets_user_id_from_session(
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
        d = date.today()
        await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        e = db.query(FuelEntry).one()
        assert e.user_id == user.id

    @pytest.mark.asyncio
    async def test_create_fuel_entry_with_notes(
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
        d = date.today()
        await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
                "notes": "Filled at station",
            },
            follow_redirects=False,
        )
        e = db.query(FuelEntry).one()
        assert e.notes == "Filled at station"

    @pytest.mark.asyncio
    async def test_create_fuel_entry_without_notes(
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
        d = date.today()
        await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        e = db.query(FuelEntry).one()
        assert e.notes is None

    @pytest.mark.asyncio
    async def test_create_fuel_entry_vehicle_from_other_group_denied(
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
        v_in_b = create_test_vehicle(group_id=g_b.id)
        auth_cookie(client, user.id, g_a.id)
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v_in_b.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text

    @pytest.mark.asyncio
    async def test_create_fuel_entry_soft_deleted_vehicle_denied(
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
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text

    @pytest.mark.asyncio
    async def test_create_fuel_entry_negative_amount_fails(
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
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "-5",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text

    @pytest.mark.asyncio
    async def test_create_fuel_entry_zero_amount_fails(
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
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "0",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text

    @pytest.mark.asyncio
    async def test_create_fuel_entry_negative_reading_fails(
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
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "-1",
                "entry_date": d.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text

    @pytest.mark.asyncio
    async def test_create_fuel_entry_future_date_fails(
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
        fut = date.today() + timedelta(days=1)
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": fut.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text

    @pytest.mark.asyncio
    async def test_create_fuel_entry_requires_contributor_role(
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
        d = date.today()
        r_get = await client.get("/fuel/new", follow_redirects=False)
        assert r_get.status_code == 403
        r_post = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        assert r_post.status_code == 403

    @pytest.mark.asyncio
    async def test_create_fuel_entry_reader_denied(
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
        d = date.today()
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(v.id),
                "fuel_amount_l": "10",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code == 403


class TestEditFuelEntry:
    @pytest.mark.asyncio
    async def test_edit_fuel_entry_valid(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=10.0,
            usage_reading=100.0,
        )
        d = date.today()
        response = await client.post(
            f"/fuel/{e.id}/edit",
            data={
                "fuel_amount_l": "55",
                "usage_reading": "200",
                "entry_date": d.isoformat(),
                "notes": "updated",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(e)
        assert e.fuel_amount_l == 55.0
        assert e.usage_reading == 200.0
        assert e.notes == "updated"

    @pytest.mark.asyncio
    async def test_edit_fuel_entry_partial_update(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        d0 = date.today() - timedelta(days=2)
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=10.0,
            usage_reading=100.0,
            entry_date=d0,
            notes="keep",
        )
        response = await client.post(
            f"/fuel/{e.id}/edit",
            data={
                "fuel_amount_l": "77",
                "usage_reading": "100",
                "entry_date": d0.isoformat(),
                "notes": "keep",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(e)
        assert e.fuel_amount_l == 77.0
        assert e.usage_reading == 100.0
        assert e.entry_date == d0
        assert e.notes == "keep"

    @pytest.mark.asyncio
    async def test_edit_fuel_entry_clears_notes(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        d0 = date.today()
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            notes="remove me",
            entry_date=d0,
        )
        response = await client.post(
            f"/fuel/{e.id}/edit",
            data={
                "fuel_amount_l": str(e.fuel_amount_l),
                "usage_reading": str(e.usage_reading),
                "entry_date": d0.isoformat(),
                "notes": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(e)
        assert e.notes is None

    @pytest.mark.asyncio
    async def test_edit_fuel_entry_wrong_group_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAAAA", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBBBB", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="contributor")
        create_test_user_group(user.id, g_b.id, role="contributor")
        v_b = create_test_vehicle(group_id=g_b.id)
        e_b = create_test_fuel_entry(
            vehicle_id=v_b.id,
            group_id=g_b.id,
            user_id=user.id,
        )
        auth_cookie(client, user.id, g_a.id)
        d = date.today()
        response = await client.post(
            f"/fuel/{e_b.id}/edit",
            data={
                "fuel_amount_l": "1",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_fuel_entry_requires_contributor_role(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        d = date.today()
        r_get = await client.get(f"/fuel/{e.id}/edit", follow_redirects=False)
        assert r_get.status_code == 403
        r_post = await client.post(
            f"/fuel/{e.id}/edit",
            data={
                "fuel_amount_l": "1",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        assert r_post.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_fuel_entry_not_found_404(
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
        d = date.today()
        response = await client.post(
            "/fuel/99999/edit",
            data={
                "fuel_amount_l": "1",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_soft_deleted_fuel_entry_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        db.query(FuelEntry).filter(FuelEntry.id == e.id).update(
            {"deleted_at": datetime.now(timezone.utc)}
        )
        db.commit()
        d = date.today()
        response = await client.post(
            f"/fuel/{e.id}/edit",
            data={
                "fuel_amount_l": "1",
                "usage_reading": "1",
                "entry_date": d.isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code == 404


class TestDeleteFuelEntry:
    @pytest.mark.asyncio
    async def test_delete_fuel_entry_as_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        response = await client.post(f"/fuel/{e.id}/delete", follow_redirects=False)
        assert response.status_code == 303
        db.refresh(e)
        assert e.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_fuel_entry_as_contributor_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        response = await client.post(f"/fuel/{e.id}/delete", follow_redirects=False)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_fuel_entry_as_reader_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        response = await client.post(f"/fuel/{e.id}/delete", follow_redirects=False)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_fuel_entry_sets_deleted_at(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        e = create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
        )
        assert e.deleted_at is None
        await client.post(f"/fuel/{e.id}/delete", follow_redirects=False)
        db.refresh(e)
        assert e.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_fuel_entry_wrong_group_denied(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAAAA", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBBBB", created_by=user.id)
        create_test_user_group(user.id, g_a.id, role="admin")
        create_test_user_group(user.id, g_b.id, role="admin")
        v_b = create_test_vehicle(group_id=g_b.id)
        e_b = create_test_fuel_entry(
            vehicle_id=v_b.id,
            group_id=g_b.id,
            user_id=user.id,
        )
        auth_cookie(client, user.id, g_a.id)
        response = await client.post(f"/fuel/{e_b.id}/delete", follow_redirects=False)
        assert response.status_code == 404
