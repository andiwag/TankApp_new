"""Capture-first fuel create flow (interface craft phase 3)."""


class TestCaptureFirstFuelForm:
    async def test_create_form_exposes_capture_flow_shell(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        html = response.text
        assert "t-capture-flow" in html
        assert "t-capture-step" in html
        assert "t-capture-progress" in html
        assert "Fahrzeug" in html
        assert "Liter" in html
        assert "Fertig" in html

    async def test_create_form_has_step_navigation_controls(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        html = response.text
        assert "Weiter" in html
        assert "Zurück" in html
        assert 'type="button"' in html
        assert "goNext" in html or "@click" in html

    async def test_create_form_liter_input_is_capture_hero(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        html = response.text
        assert 'id="fuel_amount_l"' in html
        assert "t-capture-input" in html

    async def test_edit_form_skips_capture_wizard(
        self,
        client,
        auth_group,
        create_test_vehicle,
        create_test_fuel_entry,
        db,
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Edit Tractor")
        entry = create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=100.0,
        )
        db.commit()
        response = await client.get(f"/fuel/{entry.id}/edit")
        assert response.status_code == 200
        html = response.text
        assert "t-capture-progress" not in html
        assert "Weiter" not in html
        assert 'id="fuel_amount_l"' in html

    async def test_create_form_still_posts_all_required_fields(
        self, client, auth_group, create_test_vehicle, db
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Capture Truck")
        response = await client.post(
            "/fuel/new",
            data={
                "vehicle_id": str(vehicle.id),
                "fuel_amount_l": "55.5",
                "usage_reading": "1200",
                "entry_date": "2026-07-22",
                "fill_source": "external",
                "full_tank": "1",
                "total_cost_eur": "",
                "notes": "",
                "adblue_amount_l": "",
                "fuel_tank_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        from app.models import FuelEntry

        entry = (
            db.query(FuelEntry)
            .filter(FuelEntry.group_id == group.id, FuelEntry.vehicle_id == vehicle.id)
            .one()
        )
        assert entry.fuel_amount_l == 55.5
