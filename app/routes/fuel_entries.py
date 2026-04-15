from datetime import date

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
from app.schemas import FuelEntryCreate, FuelEntryUpdate, first_validation_error_message
from app.services import fuel_entries as fuel_entry_service
from app.services import vehicles as vehicle_service

router = APIRouter()


def _fuel_form_response(
    request: Request,
    *,
    mode: str,
    vehicles: list,
    error: str | None = None,
    entry=None,
    vehicle=None,
    form_vehicle_id: str = "",
    form_fuel_amount_l: str = "",
    form_usage_reading: str = "",
    form_entry_date: str = "",
    form_notes: str = "",
):
    return templates.TemplateResponse(
        request,
        "fuel_entry_form.html",
        {
            "mode": mode,
            "vehicles": vehicles,
            "error": error,
            "entry": entry,
            "vehicle": vehicle,
            "form_vehicle_id": form_vehicle_id,
            "form_fuel_amount_l": form_fuel_amount_l,
            "form_usage_reading": form_usage_reading,
            "form_entry_date": form_entry_date,
            "form_notes": form_notes,
        },
    )


@router.get("/fuel")
async def fuel_entries_list_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    user = request.state.user
    ctx = fuel_entry_service.fuel_entries_page_context(db, user, group.id)
    return templates.TemplateResponse(request, "fuel_entries.html", context=ctx)


@router.get("/fuel/new")
async def new_fuel_entry_form(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    vehicles = vehicle_service.list_vehicles_for_group(db, group.id)
    return _fuel_form_response(
        request,
        mode="create",
        vehicles=vehicles,
        form_entry_date=date.today().isoformat(),
    )


@router.post("/fuel/new")
async def create_fuel_entry_post(
    request: Request,
    vehicle_id: str = Form(""),
    fuel_amount_l: str = Form(""),
    usage_reading: str = Form(""),
    entry_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user=Depends(require_role(Role.contributor.value)),
):
    vehicles = vehicle_service.list_vehicles_for_group(db, group.id)

    def _error_form(msg: str):
        return _fuel_form_response(
            request,
            mode="create",
            vehicles=vehicles,
            error=msg,
            form_vehicle_id=vehicle_id,
            form_fuel_amount_l=fuel_amount_l,
            form_usage_reading=usage_reading,
            form_entry_date=entry_date,
            form_notes=notes,
        )

    try:
        data = FuelEntryCreate(
            vehicle_id=int(vehicle_id),
            fuel_amount_l=float(fuel_amount_l),
            usage_reading=float(usage_reading),
            entry_date=date.fromisoformat(entry_date),
            notes=notes.strip() or None,
        )
    except ValueError:
        return _error_form("Invalid input")
    except ValidationError as exc:
        return _error_form(first_validation_error_message(exc))

    vehicle = vehicle_service.get_active_vehicle_in_group(
        db, data.vehicle_id, group.id
    )
    if not vehicle:
        return _error_form("Choose a valid vehicle from this group.")

    fuel_entry_service.create_fuel_entry(db, user.id, group.id, vehicle, data)
    response = RedirectResponse(url="/fuel", status_code=303)
    set_flash(response, "Fuel entry added.", "success")
    return response


@router.get("/fuel/{entry_id}/edit")
async def edit_fuel_entry_form(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    entry = fuel_entry_service.get_active_fuel_entry_in_group(db, entry_id, group.id)
    if not entry:
        return Response("Not found", status_code=404)
    return _fuel_form_response(
        request,
        mode="edit",
        vehicles=[],
        entry=entry,
        vehicle=entry.vehicle,
    )


@router.post("/fuel/{entry_id}/edit")
async def edit_fuel_entry_post(
    request: Request,
    entry_id: int,
    fuel_amount_l: str = Form(""),
    usage_reading: str = Form(""),
    entry_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    entry = fuel_entry_service.get_active_fuel_entry_in_group(db, entry_id, group.id)
    if not entry:
        return Response("Not found", status_code=404)

    try:
        data = FuelEntryUpdate(
            fuel_amount_l=float(fuel_amount_l),
            usage_reading=float(usage_reading),
            entry_date=date.fromisoformat(entry_date),
            notes=notes.strip() or None,
        )
    except (ValueError, ValidationError) as exc:
        msg = (
            "Invalid input"
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _fuel_form_response(
            request,
            mode="edit",
            vehicles=[],
            error=msg,
            entry=entry,
            vehicle=entry.vehicle,
        )

    fuel_entry_service.apply_fuel_entry_update(db, entry, data)
    response = RedirectResponse(url="/fuel", status_code=303)
    set_flash(response, "Fuel entry updated.", "success")
    return response


@router.post("/fuel/{entry_id}/delete")
async def delete_fuel_entry_post(
    entry_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    entry = fuel_entry_service.get_active_fuel_entry_in_group(db, entry_id, group.id)
    if not entry:
        return Response("Not found", status_code=404)

    fuel_entry_service.soft_delete_fuel_entry(db, entry)
    response = RedirectResponse(url="/fuel", status_code=303)
    set_flash(response, "Fuel entry removed.", "success")
    return response
