"""Visual polish follow-ups from craft review (icons, chips, form, seed)."""

from pathlib import Path


class TestAttentionWrenchIcon:
    def test_wrench_icon_path_is_not_link_icon(self):
        macros = Path("app/templates/_macros.html").read_text(encoding="utf-8")
        wrench_start = macros.index("{% macro icon_wrench")
        wrench_block = macros[wrench_start : macros.index("{%- endmacro %}", wrench_start)]
        link_start = macros.index("{% macro icon_link")
        link_block = macros[link_start : macros.index("{%- endmacro %}", link_start)]
        # Distinct shapes: wrench must not reuse the link path.
        assert "M13.19 8.688" not in wrench_block
        assert "M14.7 6.3" in wrench_block or "wrench" in wrench_block.lower()
        assert "M13.19 8.688" in link_block

    async def test_dashboard_attention_uses_wrench_icon_markup(
        self, client, auth_group, create_test_vehicle, db, set_group_tier
    ):
        from datetime import date, timedelta

        from app.models import MaintenanceLog

        user, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        vehicle = create_test_vehicle(group_id=group.id, name="Icon Tractor")
        db.add(
            MaintenanceLog(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                description="Ölwechsel",
                service_date=date.today(),
                next_service_date=date.today() + timedelta(days=5),
            )
        )
        db.commit()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        attention = response.text.split("t-dashboard-attention", 1)[1].split(
            "t-dashboard-metrics", 1
        )[0]
        assert "t-dashboard-attention-item__icon" in attention
        assert "M14.7 6.3" in attention


class TestChipDeslop:
    async def test_fuel_list_avoids_chip_spam(
        self, client, auth_group, create_test_vehicle, create_test_fuel_entry, db
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Chip Truck")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=100.0,
        )
        response = await client.get("/fuel")
        html = response.text.split('id="fuel-entry-list"', 1)[1]
        assert "Chip Truck" in html
        assert html.count("t-status-chip") <= 1

    async def test_vehicle_list_puts_type_in_meta_not_dual_chips(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        create_test_vehicle(group_id=group.id, name="Meta Car", vtype="car")
        response = await client.get("/vehicles")
        html = response.text.split('id="vehicle-list"', 1)[1]
        assert "Meta Car" in html
        assert html.count("t-status-chip") == 0
        assert "t-lean-list-row__meta" in html

    async def test_tanks_list_uses_fuel_meta_not_chip(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        create_test_storage_tank(
            group_id=group.id, name="Quiet Tank", fuel_type="diesel", capacity_l=1000.0
        )
        response = await client.get("/tanks")
        html = response.text
        assert "Quiet Tank" in html
        assert "Diesel" in html
        tank_block = html.split('aria-label="Tanklager"', 1)[1] if 'aria-label="Tanklager"' in html else html
        assert tank_block.count("t-status-chip") == 0

class TestCaptureFormCraft:
    async def test_create_form_uses_flat_capture_surface(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        form_start = response.text.find('action="/fuel/new"')
        form_html = response.text[form_start : response.text.find("</form>", form_start)]
        assert "t-capture-flow" in form_html
        assert "t-capture-surface" in form_html
        # Avoid panel+section double carding on create.
        assert form_html.count("t-form-section") == 0 or "t-capture-block" in form_html

    async def test_liter_input_has_hero_affordance(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        assert "t-capture-input" in response.text
        assert "t-capture-input--hero" in response.text
        assert 'inputmode="decimal"' in response.text


class TestSeedCapacity:
    def test_demo_diesel_stock_within_capacity(self, db):
        from scripts.seed_dev import clear_demo_data, seed_demo_data

        clear_demo_data(db)
        result = seed_demo_data(db)
        assert result["created"] is True
        assert "diesel_capacity_l" in result
        assert result["diesel_stock_l"] <= result["diesel_capacity_l"]
        assert result["petrol_stock_l"] <= result["petrol_capacity_l"]
