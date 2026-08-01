"""Craft foundation: domain tokens, type, tank gauge signature (phases 0–2)."""

from pathlib import Path

from app.services.storage_tanks import tank_fill_percent

APP_CSS = Path("app/static/app.css")


class TestDomainTokens:
    def test_app_css_uses_ibm_plex_not_inter(self):
        css = APP_CSS.read_text(encoding="utf-8")
        assert "IBM+Plex+Sans" in css or "IBM Plex Sans" in css
        assert "family=Inter" not in css

    def test_app_css_defines_domain_tokens(self):
        css = APP_CSS.read_text(encoding="utf-8")
        for token in (
            "--yard:",
            "--plate:",
            "--plate-inset:",
            "--seam:",
            "--ink:",
            "--mist:",
            "--enamel:",
            "--diesel:",
            "--fault:",
        ):
            assert token in css, f"missing token {token}"

    def test_lean_panel_does_not_use_lift_shadow(self):
        css = APP_CSS.read_text(encoding="utf-8")
        # Extract .t-dashboard-panel block (first occurrence).
        start = css.index(".t-dashboard-panel {")
        end = css.index("}", start)
        block = css[start:end]
        assert "box-shadow" not in block
        assert "var(--dashboard-border)" in block or "var(--seam)" in block


class TestTankFillPercent:
    def test_unknown_capacity_returns_none(self):
        assert tank_fill_percent(100.0, None) is None
        assert tank_fill_percent(100.0, 0.0) is None

    def test_empty_and_full(self):
        assert tank_fill_percent(0.0, 1000.0) == 0
        assert tank_fill_percent(1000.0, 1000.0) == 100

    def test_clamps_over_capacity_and_negative(self):
        assert tank_fill_percent(1200.0, 1000.0) == 100
        assert tank_fill_percent(-50.0, 1000.0) == 0

    def test_mid_level_rounds(self):
        assert tank_fill_percent(250.0, 1000.0) == 25


class TestTankGaugeSurfaces:
    async def test_dashboard_shows_tank_gauge_when_capacity(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        create_test_storage_tank(
            group_id=group.id,
            name="Diesel Haupttank",
            capacity_l=5000.0,
            opening_balance_l=1250.0,
        )
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "t-tank-gauge" in response.text
        assert "t-tank-gauge__fill" in response.text

    async def test_dashboard_omits_gauge_fill_without_capacity(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        create_test_storage_tank(
            group_id=group.id,
            name="Ohne Kapazität",
            capacity_l=None,
            opening_balance_l=100.0,
        )
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "Ohne Kapazität" in response.text
        assert "t-tank-gauge" not in response.text

    async def test_tanks_list_shows_gauge_when_capacity(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        create_test_storage_tank(
            group_id=group.id,
            name="Benzin",
            fuel_type="petrol",
            capacity_l=2000.0,
            opening_balance_l=500.0,
        )
        response = await client.get("/tanks")
        assert response.status_code == 200
        assert "t-tank-gauge" in response.text

    async def test_tank_detail_shows_large_gauge(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        tank = create_test_storage_tank(
            group_id=group.id,
            name="Detail-Tank",
            capacity_l=4000.0,
            opening_balance_l=1000.0,
        )
        response = await client.get(f"/tanks/{tank.id}")
        assert response.status_code == 200
        assert "t-tank-gauge" in response.text
        assert "t-tank-gauge--lg" in response.text
