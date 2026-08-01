"""Analytics narrative craft (phase 7): one hero insight per view."""


class TestAnalyticsNarrative:
    async def test_analytics_uses_story_shell(
        self, client, auth_group, set_group_tier, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        create_test_vehicle(group_id=group.id, name="Story Tractor")
        response = await client.get("/analytics")
        assert response.status_code == 200
        html = response.text
        assert "t-analytics-story" in html
        assert "t-analytics-story__value" in html
        assert "Auswertung" in html
        assert "Einblicke" not in html

    async def test_analytics_desktop_has_one_primary_story_not_equal_kpi_strip(
        self, client, auth_group, set_group_tier, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        create_test_vehicle(group_id=group.id, name="KPI Tractor")
        response = await client.get("/analytics")
        desktop = response.text.split('class="hidden lg:block', 1)[1]
        assert "t-analytics-story" in desktop
        assert 'aria-label="Kennzahlen"' not in desktop
        assert "t-analytics-facts" in desktop
        assert "monthly-chart" in desktop

    async def test_analytics_charts_use_domain_type_and_colors(
        self, client, auth_group, set_group_tier, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        create_test_vehicle(group_id=group.id)
        response = await client.get("/analytics")
        html = response.text
        assert "IBM Plex Sans" in html
        assert "Inter, sans-serif" not in html
        assert "#0d6b4f" in html

    def test_trend_delta_macro_is_instrument_not_pill(self):
        from pathlib import Path

        text = Path("app/templates/_macros.html").read_text(encoding="utf-8")
        block = text.split("{% macro trend_chip", 1)[1].split("{%- endmacro %}", 1)[0]
        assert "t-trend-delta" in block
        assert "rounded-full" not in block
        assert "t-trend-chip" not in block
