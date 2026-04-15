from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group, require_role
from app.enums import Role
from app.flash import set_flash
from app.main import templates
from app.models import Group
from app.schemas import VehicleCreate, VehicleUpdate, first_validation_error_message
from app.services import vehicles as vehicle_service

router = APIRouter()


def _vehicle_form_response(
    request: Request,
    *,
    mode: str,
    error: str | None = None,
    vehicle=None,
    form_name: str = "",
    form_vtype: str = "",
    form_fuel_type: str = "",
):
    return templates.TemplateResponse(
        request,
        "vehicle_form.html",
        {
            "mode": mode,
            "error": error,
            "vehicle": vehicle,
            "form_name": form_name,
            "form_vtype": form_vtype,
            "form_fuel_type": form_fuel_type,
        },
    )


@router.get("/vehicles")
async def vehicles_list_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    user = request.state.user
    ctx = vehicle_service.vehicles_page_context(db, user, group.id)
    return templates.TemplateResponse(request, "vehicles.html", context=ctx)


@router.get("/vehicles/new")
async def new_vehicle_form(
    request: Request,
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    return _vehicle_form_response(request, mode="create")


@router.post("/vehicles/new")
async def create_vehicle_post(
    request: Request,
    name: str = Form(""),
    vtype: str = Form(""),
    fuel_type: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    try:
        data = VehicleCreate(name=name, vtype=vtype, fuel_type=fuel_type)
    except ValidationError as exc:
        return _vehicle_form_response(
            request,
            mode="create",
            error=first_validation_error_message(exc),
            form_name=name,
            form_vtype=vtype,
            form_fuel_type=fuel_type,
        )
    vehicle_service.create_vehicle(db, group.id, data)
    response = RedirectResponse(url="/vehicles", status_code=303)
    set_flash(response, "Vehicle created.", "success")
    return response


@router.get("/vehicles/{vehicle_id}/edit")
async def edit_vehicle_form(
    request: Request,
    vehicle_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    vehicle = vehicle_service.get_active_vehicle_in_group(db, vehicle_id, group.id)
    if not vehicle:
        return Response("Not found", status_code=404)
    return _vehicle_form_response(request, mode="edit", vehicle=vehicle)


@router.post("/vehicles/{vehicle_id}/edit")
async def edit_vehicle_post(
    request: Request,
    vehicle_id: int,
    name: str = Form(""),
    fuel_type: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    vehicle = vehicle_service.get_active_vehicle_in_group(db, vehicle_id, group.id)
    if not vehicle:
        return Response("Not found", status_code=404)

    try:
        data = VehicleUpdate(
            name=name,
            fuel_type=fuel_type if fuel_type.strip() else None,
        )
    except ValidationError as exc:
        return _vehicle_form_response(
            request,
            mode="edit",
            error=first_validation_error_message(exc),
            vehicle=vehicle,
        )

    vehicle_service.apply_vehicle_update(db, vehicle, data)
    response = RedirectResponse(url="/vehicles", status_code=303)
    set_flash(response, "Vehicle updated.", "success")
    return response


@router.post("/vehicles/{vehicle_id}/delete")
async def delete_vehicle_post(
    vehicle_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    vehicle = vehicle_service.get_active_vehicle_in_group(db, vehicle_id, group.id)
    if not vehicle:
        return Response("Not found", status_code=404)

    vehicle_service.soft_delete_vehicle(db, vehicle)
    response = RedirectResponse(url="/vehicles", status_code=303)
    set_flash(response, "Vehicle removed.", "success")
    return response
