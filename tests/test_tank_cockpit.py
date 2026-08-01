"""Tank cockpit polish (phase 6) + mobile dashboard scroll end."""


class TestTankCockpit:
    async def test_tank_detail_uses_cockpit_shell(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        tank = create_test_storage_tank(
            group_id=group.id,
            name="Cockpit Tank",
            capacity_l=1000.0,
            opening_balance_l=400.0,
        )
        response = await client.get(f"/tanks/{tank.id}")
        assert response.status_code == 200
        html = response.text
        assert "t-tank-cockpit" in html
        assert "t-tank-cockpit__stock" in html
        assert "t-tank-gauge--lg" in html
        assert "Cockpit Tank" in html

    async def test_tank_detail_primary_action_and_secondary_menu(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        tank = create_test_storage_tank(group_id=group.id, name="Actions Tank")
        response = await client.get(f"/tanks/{tank.id}")
        html = response.text
        assert "t-tank-cockpit__actions" in html
        assert "Lieferung erfassen" in html
        assert "Weitere Aktionen" in html
        assert f"/tanks/{tank.id}/external/new" in html
        assert f"/tanks/{tank.id}/edit" in html

    async def test_tank_ledger_avoids_movement_type_chips(
        self, client, auth_group, create_test_storage_tank, db
    ):
        from datetime import date

        user, group = auth_group(role="admin")
        tank = create_test_storage_tank(group_id=group.id, name="Ledger Tank")
        await client.post(
            f"/tanks/{tank.id}/delivery/new",
            data={
                "amount_l": "100",
                "entry_date": date.today().isoformat(),
            },
            follow_redirects=False,
        )
        response = await client.get(f"/tanks/{tank.id}")
        ledger = response.text.split('aria-label="Bewegungen"', 1)[1]
        assert "Lieferung" in ledger
        assert ledger.count("t-status-chip") == 0
        assert "t-tank-ledger-amount" in ledger


class TestDashboardMobileScrollEnd:
    async def test_dashboard_mobile_has_scroll_end_spacer(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "t-mobile-scroll-end" in response.text
