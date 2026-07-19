from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group, require_role
from app.enums import FillSource, Role
from app.flash import set_flash
from app.form_parsing import (
    parse_bool,
    parse_date,
    parse_float,
    parse_int,
    parse_optional_float,
)
from app.models import Group
from app.responses import not_found_response
from app.schemas import FuelEntryCreate, FuelEntryUpdate, first_validation_error_message
from app.services import fuel_entries as fuel_entry_service
from app.services import vehicles as vehicle_service
from app.templating import templates

router = APIRouter()


def _fuel_form_response(
    request: Request,
    *,
    mode: str,
    vehicles: list,
    storage_tanks: list | None = None,
    error: str | None = None,
    entry=None,
    vehicle=None,
    form_vehicle_id: str = "",
    form_fuel_amount_l: str = "",
    form_usage_reading: str = "",
    form_entry_date: str = "",
    form_notes: str = "",
    form_full_tank: bool = True,
    form_total_cost_eur: str = "",
    form_adblue_amount_l: str = "",
    form_fill_source: str = "external",
    form_fuel_tank_id: str = "",
):
    return templates.TemplateResponse(
        request,
        "fuel_entry_form.html",
        {
            "mode": mode,
            "vehicles": vehicles,
            "storage_tanks": storage_tanks or [],
            "error": error,
            "entry": entry,
            "vehicle": vehicle,
            "form_vehicle_id": form_vehicle_id,
            "form_fuel_amount_l": form_fuel_amount_l,
            "form_usage_reading": form_usage_reading,
            "form_entry_date": form_entry_date,
            "form_notes": form_notes,
            "form_full_tank": form_full_tank,
            "form_total_cost_eur": form_total_cost_eur,
            "form_adblue_amount_l": form_adblue_amount_l,
            "form_fill_source": form_fill_source,
            "form_fuel_tank_id": form_fuel_tank_id,
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
    tank_ctx = fuel_entry_service.fuel_entry_form_context(db, group.id)
    return _fuel_form_response(
        request,
        mode="create",
        vehicles=vehicles,
        form_entry_date=date.today().isoformat(),
        **tank_ctx,
    )


@router.post("/fuel/new")
async def create_fuel_entry_post(
    request: Request,
    vehicle_id: str = Form(""),
    fuel_amount_l: str = Form(""),
    usage_reading: str = Form(""),
    entry_date: str = Form(""),
    notes: str = Form(""),
    full_tank: str = Form("1"),
    total_cost_eur: str = Form(""),
    adblue_amount_l: str = Form(""),
    fill_source: str = Form("external"),
    fuel_tank_id: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user=Depends(require_role(Role.contributor.value)),
):
    vehicles = vehicle_service.list_vehicles_for_group(db, group.id)
    tank_ctx = fuel_entry_service.fuel_entry_form_context(db, group.id)

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
            form_full_tank=parse_bool(full_tank),
            form_total_cost_eur=total_cost_eur,
            form_adblue_amount_l=adblue_amount_l,
            form_fill_source=fill_source,
            form_fuel_tank_id=fuel_tank_id,
            **tank_ctx,
        )

    try:
        vid = parse_int(vehicle_id, "Fahrzeug")
    except ValueError as exc:
        return _error_form(str(exc))

    vehicle = vehicle_service.get_active_vehicle_in_group(db, vid, group.id)
    if not vehicle:
        return _error_form("Bitte ein gültiges Fahrzeug aus dieser Gruppe wählen.")

    try:
        adblue = (
            parse_optional_float(adblue_amount_l, "AdBlue")
            if adblue_amount_l.strip()
            else None
        )
        tank_id = parse_int(fuel_tank_id, "Hof-Tank") if fuel_tank_id.strip() else None
        data = FuelEntryCreate(
            vehicle_id=vehicle.id,
            fuel_amount_l=parse_float(fuel_amount_l, "Kraftstoffmenge"),
            usage_reading=parse_float(usage_reading, "Betriebsstand"),
            entry_date=parse_date(entry_date, "Datum"),
            full_tank=parse_bool(full_tank),
            total_cost_eur=parse_optional_float(total_cost_eur, "Gesamtkosten"),
            adblue_amount_l=adblue,
            fill_source=fill_source,
            fuel_tank_id=tank_id,
            notes=notes.strip() or None,
        )
    except ValueError as exc:
        return _error_form(str(exc))
    except ValidationError as exc:
        return _error_form(first_validation_error_message(exc))

    try:
        fuel_entry_service.create_fuel_entry(db, user.id, group.id, vehicle, data)
    except ValueError as exc:
        return _error_form(str(exc))
    response = RedirectResponse(url="/fuel", status_code=303)
    set_flash(response, "Tankvorgang hinzugefügt.", "success")
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
        return not_found_response()
    tank_ctx = fuel_entry_service.fuel_entry_form_context(db, group.id)
    return _fuel_form_response(
        request,
        mode="edit",
        vehicles=[],
        entry=entry,
        vehicle=entry.vehicle,
        form_fill_source=entry.fill_source,
        form_fuel_tank_id=str(entry.fuel_tank_id) if entry.fuel_tank_id else "",
        **tank_ctx,
    )


@router.post("/fuel/{entry_id}/edit")
async def edit_fuel_entry_post(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user=Depends(require_role(Role.contributor.value)),
):
    entry = fuel_entry_service.get_active_fuel_entry_in_group(db, entry_id, group.id)
    if not entry:
        return not_found_response()

    tank_ctx = fuel_entry_service.fuel_entry_form_context(db, group.id)
    form = await request.form()
    try:
        update_fields: dict = {
            "fuel_amount_l": parse_float(
                form.get("fuel_amount_l", ""), "Kraftstoffmenge"
            ),
            "usage_reading": parse_float(
                form.get("usage_reading", ""), "Betriebsstand"
            ),
            "entry_date": parse_date(form.get("entry_date", ""), "Datum"),
            "notes": (form.get("notes", "") or "").strip() or None,
            "fill_source": form.get("fill_source", FillSource.external.value),
        }
        raw_tank = form.get("fuel_tank_id", "")
        if raw_tank.strip():
            update_fields["fuel_tank_id"] = parse_int(raw_tank, "Hof-Tank")
        else:
            update_fields["fuel_tank_id"] = None
        if "full_tank" in form:
            update_fields["full_tank"] = parse_bool(form["full_tank"])
        if "total_cost_eur" in form:
            update_fields["total_cost_eur"] = parse_optional_float(
                form.get("total_cost_eur", ""), "Gesamtkosten"
            )
        if entry.vehicle.vtype == "tractor":
            raw_adblue = form.get("adblue_amount_l", "")
            if raw_adblue.strip():
                update_fields["adblue_amount_l"] = parse_float(raw_adblue, "AdBlue")
            else:
                update_fields["adblue_amount_l"] = None
        data = FuelEntryUpdate(**update_fields)
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
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
            form_fill_source=form.get("fill_source", entry.fill_source),
            form_fuel_tank_id=form.get("fuel_tank_id", ""),
            **tank_ctx,
        )

    try:
        fuel_entry_service.apply_fuel_entry_update(
            db,
            entry,
            data,
            vehicle=entry.vehicle,
            user_id=user.id,
            group_id=group.id,
        )
    except ValueError as exc:
        return _fuel_form_response(
            request,
            mode="edit",
            vehicles=[],
            error=str(exc),
            entry=entry,
            vehicle=entry.vehicle,
            form_fill_source=form.get("fill_source", entry.fill_source),
            form_fuel_tank_id=form.get("fuel_tank_id", ""),
            **tank_ctx,
        )
    response = RedirectResponse(url="/fuel", status_code=303)
    set_flash(response, "Tankvorgang aktualisiert.", "success")
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
        return not_found_response()

    fuel_entry_service.soft_delete_fuel_entry(db, entry)
    response = RedirectResponse(url="/fuel", status_code=303)
    set_flash(response, "Tankvorgang entfernt.", "success")
    return response
