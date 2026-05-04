"""Tests for Phase 15: PWA support."""

import struct


def _png_dimensions(content: bytes) -> tuple[int, int]:
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    assert content[12:16] == b"IHDR"
    return struct.unpack(">II", content[16:24])


class TestManifest:
    async def test_manifest_json_accessible(self, client):
        response = await client.get("/static/manifest.json")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    async def test_manifest_json_valid_structure(self, client):
        response = await client.get("/static/manifest.json")

        manifest = response.json()
        assert manifest["name"] == "TankApp"
        assert manifest["short_name"] == "TankApp"
        assert manifest["display"] == "standalone"
        assert manifest["start_url"] == "/dashboard"
        assert manifest["scope"] == "/"
        assert len(manifest["icons"]) == 2
        assert {
            "src": "/static/icon-192.png",
            "sizes": "192x192",
            "type": "image/png",
        } in manifest["icons"]
        assert {
            "src": "/static/icon-512.png",
            "sizes": "512x512",
            "type": "image/png",
        } in manifest["icons"]


class TestServiceWorker:
    async def test_service_worker_accessible(self, client):
        response = await client.get("/static/sw.js")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/javascript")
        assert "self.addEventListener('install'" in response.text
        assert "caches.open" in response.text
        assert "/static/manifest.json" in response.text


class TestBaseTemplatePwa:
    async def test_base_template_includes_manifest_link(self, client):
        response = await client.get("/login")

        assert response.status_code == 200
        assert '<link rel="manifest" href="/static/manifest.json">' in response.text

    async def test_base_template_registers_service_worker(self, client):
        response = await client.get("/login")

        assert response.status_code == 200
        assert "navigator.serviceWorker.register('/static/sw.js')" in response.text


class TestPwaIcons:
    async def test_pwa_icons_accessible(self, client):
        expected_icons = [
            ("/static/icon-192.png", (192, 192)),
            ("/static/icon-512.png", (512, 512)),
        ]

        for path, expected_dimensions in expected_icons:
            response = await client.get(path)

            assert response.status_code == 200, path
            assert response.headers["content-type"].startswith("image/png")
            assert _png_dimensions(response.content) == expected_dimensions
