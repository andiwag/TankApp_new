from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest
import segno
from app.auth import decode_session_cookie
from app.config import settings
from app.main import app
from app.models import FuelEntry, TankLedgerEntry, Vehicle
from app.services.vehicle_qr import (
    QrConfigurationError,
    QrGenerationError,
    vehicle_qr_svg,
    vehicle_quick_capture_url,
)
from app.time_utils import utc_now
from httpx import ASGITransport, AsyncClient

from tests.conftest import create_authenticated_group


class TestVehicleQuickFuelCapture:
    async def test_scan_requires_login_and_preserves_quick_capture_destination(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=group.id)
        target = f"/fuel/quick/{group.id}/{vehicle.id}"

        response = await client.get(target, follow_redirects=False)

        login_url = urlsplit(response.headers["location"])
        assert response.status_code == 303
        assert login_url.path == "/login"
        assert parse_qs(login_url.query) == {"next": [target]}

    async def test_quick_capture_uses_target_farm_without_switching_active_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        active_group = create_test_group(
            name="Active Farm", invite_code="FARM-ACTIVE", created_by=user.id
        )
        target_group = create_test_group(
            name="QR Farm", invite_code="FARM-QR-TARGET", created_by=user.id
        )
        create_test_user_group(user.id, active_group.id, role="contributor")
        create_test_user_group(user.id, target_group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=target_group.id, name="QR Tractor")
        auth_cookie(client, user.id, active_group.id)

        response = await client.get(f"/fuel/quick/{target_group.id}/{vehicle.id}")

        assert response.status_code == 200
        assert "QR Farm" in response.text
        assert "QR Tractor" in response.text
        assert db.query(FuelEntry).count() == 0
        assert db.query(TankLedgerEntry).count() == 0
        session_data = decode_session_cookie(
            client.cookies.get(settings.SESSION_COOKIE_NAME)
        )
        assert session_data["active_group_id"] == active_group.id

    async def test_quick_capture_farm_fill_uses_target_farm_ledger(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        active_group = create_test_group(
            name="Active Farm", invite_code="FARM-LEDGER-A", created_by=user.id
        )
        target_group = create_test_group(
            name="Tank Farm", invite_code="FARM-LEDGER-B", created_by=user.id
        )
        create_test_user_group(user.id, active_group.id, role="contributor")
        create_test_user_group(user.id, target_group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=target_group.id)
        tank = create_test_storage_tank(group_id=target_group.id, opening_balance_l=500)
        auth_cookie(client, user.id, active_group.id)

        response = await client.post(
            f"/fuel/quick/{target_group.id}/{vehicle.id}",
            data={
                "fuel_amount_l": "25",
                "usage_reading": "55",
                "entry_date": date.today().isoformat(),
                "fill_source": "farm",
                "fuel_tank_id": str(tank.id),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        entry = db.query(FuelEntry).one()
        ledger = db.query(TankLedgerEntry).one()
        assert entry.group_id == target_group.id
        assert entry.vehicle_id == vehicle.id
        assert ledger.group_id == target_group.id
        assert ledger.tank_id == tank.id
        assert ledger.amount_l == -25

    async def test_quick_capture_post_uses_route_vehicle_and_target_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        active_group = create_test_group(
            name="Active Farm", invite_code="FARM-POST-A", created_by=user.id
        )
        target_group = create_test_group(
            name="Target Farm", invite_code="FARM-POST-B", created_by=user.id
        )
        create_test_user_group(user.id, active_group.id, role="contributor")
        create_test_user_group(user.id, target_group.id, role="contributor")
        target_vehicle = create_test_vehicle(
            group_id=target_group.id, name="Target Tractor"
        )
        other_vehicle = create_test_vehicle(
            group_id=active_group.id, name="Other Tractor"
        )
        auth_cookie(client, user.id, active_group.id)
        target = f"/fuel/quick/{target_group.id}/{target_vehicle.id}"

        response = await client.post(
            target,
            data={
                "vehicle_id": str(other_vehicle.id),
                "fuel_amount_l": "42.5",
                "usage_reading": "1000",
                "entry_date": date.today().isoformat(),
                "fill_source": "external",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == target
        entry = db.query(FuelEntry).one()
        assert entry.vehicle_id == target_vehicle.id
        assert entry.group_id == target_group.id
        assert entry.user_id == user.id
        session_data = decode_session_cookie(
            client.cookies.get(settings.SESSION_COOKIE_NAME)
        )
        assert session_data["active_group_id"] == active_group.id

    async def test_quick_capture_denies_reader(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="reader")
        vehicle = create_test_vehicle(group_id=group.id)
        auth_cookie(client, user.id, group.id)

        response = await client.get(f"/fuel/quick/{group.id}/{vehicle.id}")

        assert response.status_code == 403

    async def test_quick_capture_post_denies_reader_without_creating_entry(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="reader")
        vehicle = create_test_vehicle(group_id=group.id)
        auth_cookie(client, user.id, group.id)

        response = await client.post(
            f"/fuel/quick/{group.id}/{vehicle.id}",
            data={
                "fuel_amount_l": "20",
                "usage_reading": "50",
                "entry_date": date.today().isoformat(),
            },
        )

        assert response.status_code == 403
        assert db.query(FuelEntry).count() == 0

    async def test_quick_capture_post_requires_csrf(
        self,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        client,
        db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=group.id)
        auth_cookie(client, user.id, group.id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as raw:
            raw.cookies.set(
                settings.SESSION_COOKIE_NAME,
                client.cookies.get(settings.SESSION_COOKIE_NAME),
            )
            response = await raw.post(
                f"/fuel/quick/{group.id}/{vehicle.id}",
                data={
                    "fuel_amount_l": "20",
                    "usage_reading": "50",
                    "entry_date": date.today().isoformat(),
                },
            )

        assert response.status_code == 403
        assert db.query(FuelEntry).count() == 0

    async def test_quick_capture_rejects_foreign_farm_tank(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        active_group = create_test_group(
            name="Active Farm", invite_code="FARM-TANK-A", created_by=user.id
        )
        target_group = create_test_group(
            name="Target Farm", invite_code="FARM-TANK-B", created_by=user.id
        )
        create_test_user_group(user.id, active_group.id, role="contributor")
        create_test_user_group(user.id, target_group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=target_group.id)
        foreign_tank = create_test_storage_tank(
            group_id=active_group.id, fuel_type="diesel", opening_balance_l=500
        )
        auth_cookie(client, user.id, active_group.id)

        response = await client.post(
            f"/fuel/quick/{target_group.id}/{vehicle.id}",
            data={
                "fuel_amount_l": "20",
                "usage_reading": "50",
                "entry_date": date.today().isoformat(),
                "fill_source": "farm",
                "fuel_tank_id": str(foreign_tank.id),
            },
        )

        assert response.status_code == 200
        assert "gültigen Hof-Tank" in response.text
        assert db.query(FuelEntry).count() == 0
        assert db.query(TankLedgerEntry).count() == 0

    async def test_quick_capture_rejects_wrong_fuel_type_tank(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
        db,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        vehicle = create_test_vehicle(group_id=group.id, fuel_type="diesel")
        petrol_tank = create_test_storage_tank(
            group_id=group.id, fuel_type="petrol", opening_balance_l=500
        )

        response = await client.post(
            f"/fuel/quick/{group.id}/{vehicle.id}",
            data={
                "fuel_amount_l": "20",
                "usage_reading": "50",
                "entry_date": date.today().isoformat(),
                "fill_source": "farm",
                "fuel_tank_id": str(petrol_tank.id),
            },
        )

        assert response.status_code == 200
        assert "Kraftstofftyp des Tanks passt nicht zum Fahrzeug" in response.text
        assert db.query(FuelEntry).count() == 0
        assert db.query(TankLedgerEntry).count() == 0

    async def test_quick_capture_post_rechecks_membership_after_form_load(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        membership = create_test_user_group(user.id, group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=group.id)
        auth_cookie(client, user.id, group.id)
        target = f"/fuel/quick/{group.id}/{vehicle.id}"
        form_response = await client.get(target)
        db.delete(membership)
        db.commit()

        response = await client.post(
            target,
            data={
                "fuel_amount_l": "20",
                "usage_reading": "50",
                "entry_date": date.today().isoformat(),
            },
        )

        assert form_response.status_code == 200
        assert response.status_code == 404
        assert db.query(FuelEntry).count() == 0

    async def test_quick_capture_post_rejects_vehicle_deleted_after_form_load(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        vehicle = create_test_vehicle(group_id=group.id)
        target = f"/fuel/quick/{group.id}/{vehicle.id}"
        form_response = await client.get(target)
        db.query(Vehicle).filter(Vehicle.id == vehicle.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()

        response = await client.post(
            target,
            data={
                "fuel_amount_l": "20",
                "usage_reading": "50",
                "entry_date": date.today().isoformat(),
            },
        )

        assert form_response.status_code == 200
        assert response.status_code == 404
        assert db.query(FuelEntry).count() == 0

    async def test_quick_capture_hides_nonmember_target(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        auth_cookie(client, user.id, None)

        response = await client.get(f"/fuel/quick/{group.id}/{vehicle.id}")

        assert response.status_code == 404

    async def test_quick_capture_rejects_vehicle_from_different_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        first_group = create_test_group(
            name="First Farm", invite_code="FARM-CHECK-A", created_by=user.id
        )
        second_group = create_test_group(
            name="Second Farm", invite_code="FARM-CHECK-B", created_by=user.id
        )
        create_test_user_group(user.id, first_group.id, role="contributor")
        create_test_user_group(user.id, second_group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=second_group.id)
        auth_cookie(client, user.id, first_group.id)

        response = await client.get(f"/fuel/quick/{first_group.id}/{vehicle.id}")

        assert response.status_code == 404

    async def test_quick_capture_rejects_soft_deleted_vehicle(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        vehicle = create_test_vehicle(group_id=group.id)
        db.query(Vehicle).filter(Vehicle.id == vehicle.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()

        response = await client.get(f"/fuel/quick/{group.id}/{vehicle.id}")

        assert response.status_code == 404


class TestVehicleQrLabels:
    async def test_print_all_labels_only_includes_active_vehicles_in_active_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
        db,
    ):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example")
        user = create_test_user()
        group = create_test_group(
            name="Printable Farm", invite_code="FARM-PRINT-A", created_by=user.id
        )
        other_group = create_test_group(
            name="Other Farm", invite_code="FARM-PRINT-B", created_by=user.id
        )
        create_test_user_group(user.id, group.id, role="contributor")
        create_test_user_group(user.id, other_group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=group.id, name="Included Tractor")
        deleted_vehicle = create_test_vehicle(group_id=group.id, name="Deleted Tractor")
        create_test_vehicle(group_id=other_group.id, name="Foreign Tractor")
        db.query(Vehicle).filter(Vehicle.id == deleted_vehicle.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/vehicles/qr-labels")

        assert response.status_code == 200
        assert "Included Tractor" in response.text
        assert "Printable Farm" in response.text
        assert "Deleted Tractor" not in response.text
        assert "Foreign Tractor" not in response.text
        assert f"/vehicles/{vehicle.id}/qr.svg?v=2" in response.text

    async def test_print_one_vehicle_label_is_scoped_to_active_farm(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example")
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        other_group = create_test_group(
            name="Other Farm", invite_code="FARM-ONE-OTHER", created_by=user.id
        )
        create_test_user_group(user.id, group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=group.id, name="Single Label Tractor")
        foreign_vehicle = create_test_vehicle(
            group_id=other_group.id, name="Foreign Label Tractor"
        )
        auth_cookie(client, user.id, group.id)

        response = await client.get(f"/vehicles/{vehicle.id}/qr-label")
        foreign_response = await client.get(f"/vehicles/{foreign_vehicle.id}/qr-label")

        assert response.status_code == 200
        assert "Single Label Tractor" in response.text
        assert "t-qr-label__action" not in response.text
        assert "t-qr-label-grid--single" in response.text
        assert "inline-flex min-h-[38px]" in response.text
        assert "t-btn-primary" in response.text
        assert foreign_response.status_code == 404

    async def test_qr_svg_is_generated_locally_from_canonical_base_url(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example/")
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        vehicle = create_test_vehicle(group_id=group.id)

        response = await client.get(f"/vehicles/{vehicle.id}/qr.svg")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert response.headers["cache-control"] == "private, no-store"
        assert "<svg" in response.text
        assert 'xmlns="http://www.w3.org/2000/svg"' in response.text

    async def test_qr_svg_generation_failure_returns_controlled_response(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
        caplog,
    ):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example")
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        vehicle = create_test_vehicle(group_id=group.id)

        def fail_make_qr(*_args, **_kwargs):
            raise segno.DataOverflowError

        monkeypatch.setattr("app.services.vehicle_qr.segno.make_qr", fail_make_qr)

        response = await client.get(f"/vehicles/{vehicle.id}/qr.svg")

        assert response.status_code == 503
        assert "QR" in response.text
        assert "vehicle qr generation failed" in caplog.text.lower()

    async def test_unexpected_qr_error_uses_global_error_handler(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
        caplog,
    ):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example")
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        vehicle = create_test_vehicle(group_id=group.id)

        def fail_make_qr(*_args, **_kwargs):
            raise RuntimeError("unexpected encoder failure")

        monkeypatch.setattr("app.services.vehicle_qr.segno.make_qr", fail_make_qr)

        response = await client.get(f"/vehicles/{vehicle.id}/qr.svg")

        assert response.status_code == 500
        assert "Unhandled error on GET" in caplog.text

    async def test_printing_without_base_url_shows_setup_error(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "BASE_URL", "")
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )

        response = await client.get("/vehicles/qr-labels")

        assert response.status_code == 503
        assert "BASE_URL" in response.text

    async def test_reader_cannot_open_print_labels(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="reader")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/vehicles/qr-labels")

        assert response.status_code == 403


class TestLoginContinuation:
    async def test_login_returns_to_safe_vehicle_quick_capture(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
    ):
        user = create_test_user(password="secret1234")
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        vehicle = create_test_vehicle(group_id=group.id)
        target = f"/fuel/quick/{group.id}/{vehicle.id}"

        login_page = await client.get(f"/login?next={target}")
        response = await client.post(
            "/login",
            data={
                "email": user.email,
                "password": "secret1234",
                "next": target,
            },
            follow_redirects=False,
        )

        assert f'value="{target}"' in login_page.text
        assert response.status_code == 303
        assert response.headers["location"] == target

    async def test_login_rejects_external_return_url(self, client, create_test_user):
        user = create_test_user(password="secret1234")

        page = await client.get("/login?next=https://attacker.example")
        response = await client.post(
            "/login",
            data={
                "email": user.email,
                "password": "secret1234",
                "next": "//attacker.example/path",
            },
            follow_redirects=False,
        )

        assert 'name="next" value=""' in page.text
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"


class TestVehicleQrService:
    def test_quick_capture_url_uses_configured_canonical_origin(self, monkeypatch):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example/")

        url = vehicle_quick_capture_url(12, 34)

        assert url == "https://tankly.example/fuel/quick/12/34"

    def test_qr_svg_translates_segno_overflow(self, monkeypatch):
        monkeypatch.setattr(settings, "BASE_URL", "https://tankly.example")

        def fail_make_qr(*_args, **_kwargs):
            raise segno.DataOverflowError

        monkeypatch.setattr("app.services.vehicle_qr.segno.make_qr", fail_make_qr)

        with pytest.raises(QrGenerationError) as error:
            vehicle_qr_svg(12, 34)

        assert isinstance(error.value.__cause__, segno.DataOverflowError)

    @pytest.mark.parametrize(
        "base_url",
        [
            "",
            "tankly.example",
            "https://tankly.example/app",
            "https://user:pass@tankly.example",
            "https://[::1",
            "https://tankly.example:invalid",
            "https://tankly.example:0",
            "https://tankly.example:65536",
        ],
    )
    def test_quick_capture_url_rejects_invalid_base_url(self, monkeypatch, base_url):
        monkeypatch.setattr(settings, "BASE_URL", base_url)

        with pytest.raises(QrConfigurationError):
            vehicle_quick_capture_url(12, 34)

    def test_production_qr_url_requires_https(self, monkeypatch):
        monkeypatch.setattr(settings, "ENV", "production")
        monkeypatch.setattr(settings, "BASE_URL", "http://tankly.example")

        with pytest.raises(QrConfigurationError):
            vehicle_quick_capture_url(12, 34)

    def test_development_qr_url_allows_http(self, monkeypatch):
        monkeypatch.setattr(settings, "ENV", "development")
        monkeypatch.setattr(settings, "BASE_URL", "http://localhost:8000")

        assert vehicle_quick_capture_url(12, 34) == (
            "http://localhost:8000/fuel/quick/12/34"
        )
