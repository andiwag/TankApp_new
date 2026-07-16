from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.dependencies import require_entitlement, require_role
from app.enums import Role
from app.flash import set_flash
from app.form_parsing import (
    parse_date,
    parse_int,
    parse_optional_date,
    parse_optional_float,
)
from app.models import Group
from app.responses import not_found_response
from app.schemas import (
    MaintenanceLogCreate,
    MaintenanceLogUpdate,
    first_validation_error_message,
)
from app.services import maintenance as maintenance_service
from app.services import vehicles as vehicle_service
from app.templating import templates

router = APIRouter()


def _maintenance_form_response(
    request: Request,
    *,
    mode: str,
    vehicles: list,
    error: str | None = None,
    log=None,
    vehicle=None,
    form_vehicle_id: str = "",
    form_service_date: str = "",
    form_usage_reading: str = "",
    form_description: str = "",
    form_cost_eur: str = "",
    form_next_service_date: str = "",
    form_next_service_usage: str = "",
):
    return templates.TemplateResponse(
        request,
        "maintenance_form.html",
        {
            "mode": mode,
            "vehicles": vehicles,
            "error": error,
            "log": log,
            "vehicle": vehicle,
            "form_vehicle_id": form_vehicle_id,
            "form_service_date": form_service_date,
            "form_usage_reading": form_usage_reading,
            "form_description": form_description,
            "form_cost_eur": form_cost_eur,
            "form_next_service_date": form_next_service_date,
            "form_next_service_usage": form_next_service_usage,
        },
    )


@router.get("/maintenance")
async def maintenance_list_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("maintenance")),
):
    user = request.state.user
    ctx = maintenance_service.maintenance_page_context(db, user, group.id)
    return templates.TemplateResponse(request, "maintenance.html", context=ctx)


@router.get("/maintenance/new")
async def new_maintenance_form(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("maintenance")),
    _user=Depends(require_role(Role.contributor.value)),
):
    vehicles = vehicle_service.list_vehicles_for_group(db, group.id)
    return _maintenance_form_response(
        request,
        mode="create",
        vehicles=vehicles,
        form_service_date=date.today().isoformat(),
    )


@router.post("/maintenance/new")
async def create_maintenance_post(
    request: Request,
    vehicle_id: str = Form(""),
    service_date: str = Form(""),
    usage_reading: str = Form(""),
    description: str = Form(""),
    cost_eur: str = Form(""),
    next_service_date: str = Form(""),
    next_service_usage: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("maintenance")),
    user=Depends(require_role(Role.contributor.value)),
):
    vehicles = vehicle_service.list_vehicles_for_group(db, group.id)

    def _error_form(msg: str):
        return _maintenance_form_response(
            request,
            mode="create",
            vehicles=vehicles,
            error=msg,
            form_vehicle_id=vehicle_id,
            form_service_date=service_date,
            form_usage_reading=usage_reading,
            form_description=description,
            form_cost_eur=cost_eur,
            form_next_service_date=next_service_date,
            form_next_service_usage=next_service_usage,
        )

    try:
        data = MaintenanceLogCreate(
            vehicle_id=parse_int(vehicle_id, "Fahrzeug"),
            service_date=parse_date(service_date, "Servicedatum"),
            usage_reading=parse_optional_float(usage_reading, "Betriebsstand"),
            description=description.strip(),
            cost_eur=parse_optional_float(cost_eur, "Kosten"),
            next_service_date=parse_optional_date(
                next_service_date, "Nächstes Servicedatum"
            ),
            next_service_usage=parse_optional_float(
                next_service_usage, "Nächster Betriebsstand"
            ),
        )
    except ValueError as exc:
        return _error_form(str(exc))
    except ValidationError as exc:
        return _error_form(first_validation_error_message(exc))

    vehicle = vehicle_service.get_active_vehicle_in_group(db, data.vehicle_id, group.id)
    if not vehicle:
        return _error_form("Bitte ein gültiges Fahrzeug aus dieser Gruppe wählen.")

    log = maintenance_service.create_maintenance_log(
        db, user.id, group.id, vehicle, data
    )
    log_event(db, group.id, user.id, "maintenance.create", "maintenance", log.id)
    db.commit()
    response = RedirectResponse(url="/maintenance", status_code=303)
    set_flash(response, "Wartungseintrag hinzugefügt.", "success")
    return response


@router.get("/maintenance/{log_id}/edit")
async def edit_maintenance_form(
    request: Request,
    log_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("maintenance")),
    _user=Depends(require_role(Role.contributor.value)),
):
    log = maintenance_service.get_active_maintenance_log_in_group(db, log_id, group.id)
    if not log:
        return not_found_response()
    return _maintenance_form_response(
        request,
        mode="edit",
        vehicles=[],
        log=log,
        vehicle=log.vehicle,
    )


@router.post("/maintenance/{log_id}/edit")
async def edit_maintenance_post(
    request: Request,
    log_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("maintenance")),
    _user=Depends(require_role(Role.contributor.value)),
):
    log = maintenance_service.get_active_maintenance_log_in_group(db, log_id, group.id)
    if not log:
        return not_found_response()

    form = await request.form()
    try:
        update_fields: dict = {
            "service_date": parse_date(form.get("service_date", ""), "Servicedatum"),
            "description": (form.get("description", "") or "").strip(),
        }
        if "usage_reading" in form:
            update_fields["usage_reading"] = parse_optional_float(
                form.get("usage_reading", ""), "Betriebsstand"
            )
        if "cost_eur" in form:
            update_fields["cost_eur"] = parse_optional_float(
                form.get("cost_eur", ""), "Kosten"
            )
        if "next_service_date" in form:
            update_fields["next_service_date"] = parse_optional_date(
                form.get("next_service_date", ""), "Nächstes Servicedatum"
            )
        if "next_service_usage" in form:
            update_fields["next_service_usage"] = parse_optional_float(
                form.get("next_service_usage", ""), "Nächster Betriebsstand"
            )
        data = MaintenanceLogUpdate(**update_fields)
        maintenance_service.apply_maintenance_log_update(db, log, data)
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _maintenance_form_response(
            request,
            mode="edit",
            vehicles=[],
            error=msg,
            log=log,
            vehicle=log.vehicle,
        )

    log_event(
        db, group.id, request.state.user.id, "maintenance.update", "maintenance", log.id
    )
    db.commit()
    response = RedirectResponse(url="/maintenance", status_code=303)
    set_flash(response, "Wartungseintrag aktualisiert.", "success")
    return response


@router.post("/maintenance/{log_id}/delete")
async def delete_maintenance_post(
    request: Request,
    log_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("maintenance")),
    user=Depends(require_role(Role.admin.value)),
):
    log = maintenance_service.get_active_maintenance_log_in_group(db, log_id, group.id)
    if not log:
        return not_found_response()

    maintenance_service.soft_delete_maintenance_log(db, log)
    log_event(db, group.id, user.id, "maintenance.delete", "maintenance", log.id)
    db.commit()
    response = RedirectResponse(url="/maintenance", status_code=303)
    set_flash(response, "Wartungseintrag entfernt.", "success")
    return response
