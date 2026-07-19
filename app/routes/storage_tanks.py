from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group, require_role
from app.enums import Role
from app.flash import set_flash
from app.form_parsing import parse_date, parse_float, parse_optional_float
from app.models import Group
from app.responses import not_found_response
from app.schemas import (
    StorageTankCreate,
    StorageTankUpdate,
    TankAdjustmentCreate,
    TankDeliveryCreate,
    TankExternalWithdrawalCreate,
    first_validation_error_message,
)
from app.services import storage_tanks as tank_service
from app.services import tank_ledger as ledger_service
from app.templating import templates

router = APIRouter()


def _tank_form_response(
    request: Request,
    *,
    mode: str,
    error: str | None = None,
    tank=None,
    form_name: str = "",
    form_fuel_type: str = "",
    form_opening_balance_l: str = "0",
    form_capacity_l: str = "",
    form_notes: str = "",
):
    return templates.TemplateResponse(
        request,
        "tank_form.html",
        {
            "mode": mode,
            "error": error,
            "tank": tank,
            "form_name": form_name,
            "form_fuel_type": form_fuel_type,
            "form_opening_balance_l": form_opening_balance_l,
            "form_capacity_l": form_capacity_l,
            "form_notes": form_notes,
        },
    )


def _delivery_form_response(
    request: Request,
    *,
    tank,
    error: str | None = None,
    form_amount_l: str = "",
    form_entry_date: str = "",
    form_total_cost_eur: str = "",
    form_notes: str = "",
):
    return templates.TemplateResponse(
        request,
        "tank_delivery_form.html",
        {
            "tank": tank,
            "error": error,
            "form_amount_l": form_amount_l,
            "form_entry_date": form_entry_date,
            "form_total_cost_eur": form_total_cost_eur,
            "form_notes": form_notes,
        },
    )


def _adjustment_form_response(
    request: Request,
    *,
    tank,
    error: str | None = None,
    form_amount_l: str = "",
    form_entry_date: str = "",
    form_notes: str = "",
):
    return templates.TemplateResponse(
        request,
        "tank_adjustment_form.html",
        {
            "tank": tank,
            "error": error,
            "form_amount_l": form_amount_l,
            "form_entry_date": form_entry_date,
            "form_notes": form_notes,
        },
    )


def _external_form_response(
    request: Request,
    *,
    tank,
    error: str | None = None,
    form_amount_l: str = "",
    form_entry_date: str = "",
    form_recipient_name: str = "",
    form_total_cost_eur: str = "",
    form_notes: str = "",
):
    return templates.TemplateResponse(
        request,
        "tank_external_form.html",
        {
            "tank": tank,
            "error": error,
            "form_amount_l": form_amount_l,
            "form_entry_date": form_entry_date,
            "form_recipient_name": form_recipient_name,
            "form_total_cost_eur": form_total_cost_eur,
            "form_notes": form_notes,
        },
    )


@router.get("/tanks")
async def tanks_list_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    user = request.state.user
    ctx = tank_service.tanks_page_context(db, user, group.id)
    return templates.TemplateResponse(request, "tanks.html", context=ctx)


@router.get("/tanks/new")
async def new_tank_form(
    request: Request,
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    return _tank_form_response(request, mode="create")


@router.post("/tanks/new")
async def create_tank_post(
    request: Request,
    name: str = Form(""),
    fuel_type: str = Form(""),
    opening_balance_l: str = Form("0"),
    capacity_l: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    try:
        data = StorageTankCreate(
            name=name,
            fuel_type=fuel_type,
            opening_balance_l=parse_float(opening_balance_l or "0", "Anfangsbestand"),
            capacity_l=parse_optional_float(capacity_l, "Kapazität")
            if capacity_l.strip()
            else None,
            notes=notes.strip() or None,
        )
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _tank_form_response(
            request,
            mode="create",
            error=msg,
            form_name=name,
            form_fuel_type=fuel_type,
            form_opening_balance_l=opening_balance_l,
            form_capacity_l=capacity_l,
            form_notes=notes,
        )

    tank_service.create_storage_tank(db, group.id, data)
    response = RedirectResponse(url="/tanks", status_code=303)
    set_flash(response, "Tanklager angelegt.", "success")
    return response


@router.get("/tanks/{tank_id}")
async def tank_detail_page(
    request: Request,
    tank_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    user = request.state.user
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()
    ctx = tank_service.tank_detail_context(db, user, group.id, tank)
    return templates.TemplateResponse(request, "tank_detail.html", context=ctx)


@router.get("/tanks/{tank_id}/edit")
async def edit_tank_form(
    request: Request,
    tank_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()
    return _tank_form_response(request, mode="edit", tank=tank)


@router.post("/tanks/{tank_id}/edit")
async def edit_tank_post(
    request: Request,
    tank_id: int,
    name: str = Form(""),
    capacity_l: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()

    try:
        update_fields: dict = {"name": name.strip() or None}
        if capacity_l.strip():
            update_fields["capacity_l"] = parse_float(capacity_l, "Kapazität")
        else:
            update_fields["capacity_l"] = None
        update_fields["notes"] = notes.strip() or None
        data = StorageTankUpdate(**update_fields)
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _tank_form_response(request, mode="edit", error=msg, tank=tank)

    tank_service.apply_storage_tank_update(db, tank, data)
    response = RedirectResponse(url=f"/tanks/{tank.id}", status_code=303)
    set_flash(response, "Tanklager aktualisiert.", "success")
    return response


@router.post("/tanks/{tank_id}/delete")
async def delete_tank_post(
    tank_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()
    try:
        tank_service.soft_delete_storage_tank(db, tank)
    except ValueError as exc:
        response = RedirectResponse(url=f"/tanks/{tank.id}", status_code=303)
        set_flash(response, str(exc), "error")
        return response
    response = RedirectResponse(url="/tanks", status_code=303)
    set_flash(response, "Tanklager entfernt.", "success")
    return response


@router.get("/tanks/{tank_id}/delivery/new")
async def new_delivery_form(
    request: Request,
    tank_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()
    return _delivery_form_response(
        request, tank=tank, form_entry_date=date.today().isoformat()
    )


@router.post("/tanks/{tank_id}/delivery/new")
async def create_delivery_post(
    request: Request,
    tank_id: int,
    amount_l: str = Form(""),
    entry_date: str = Form(""),
    total_cost_eur: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user=Depends(require_role(Role.contributor.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()

    def _error(msg: str):
        return _delivery_form_response(
            request,
            tank=tank,
            error=msg,
            form_amount_l=amount_l,
            form_entry_date=entry_date,
            form_total_cost_eur=total_cost_eur,
            form_notes=notes,
        )

    try:
        data = TankDeliveryCreate(
            amount_l=parse_float(amount_l, "Menge"),
            entry_date=parse_date(entry_date, "Datum"),
            total_cost_eur=parse_optional_float(total_cost_eur, "Kosten")
            if total_cost_eur.strip()
            else None,
            notes=notes.strip() or None,
        )
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _error(msg)

    try:
        ledger_service.post_delivery(db, user.id, group.id, tank, data)
    except ValueError as exc:
        return _error(str(exc))

    response = RedirectResponse(url=f"/tanks/{tank.id}", status_code=303)
    set_flash(response, "Lieferung erfasst.", "success")
    return response


@router.get("/tanks/{tank_id}/adjustment/new")
async def new_adjustment_form(
    request: Request,
    tank_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()
    return _adjustment_form_response(
        request, tank=tank, form_entry_date=date.today().isoformat()
    )


@router.post("/tanks/{tank_id}/adjustment/new")
async def create_adjustment_post(
    request: Request,
    tank_id: int,
    amount_l: str = Form(""),
    entry_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user=Depends(require_role(Role.admin.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()

    def _error(msg: str):
        return _adjustment_form_response(
            request,
            tank=tank,
            error=msg,
            form_amount_l=amount_l,
            form_entry_date=entry_date,
            form_notes=notes,
        )

    try:
        data = TankAdjustmentCreate(
            amount_l=parse_float(amount_l, "Menge"),
            entry_date=parse_date(entry_date, "Datum"),
            notes=notes,
        )
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _error(msg)

    try:
        ledger_service.post_adjustment(db, user.id, group.id, tank, data)
    except ValueError as exc:
        return _error(str(exc))

    response = RedirectResponse(url=f"/tanks/{tank.id}", status_code=303)
    set_flash(response, "Bestandskorrektur erfasst.", "success")
    return response


@router.get("/tanks/{tank_id}/external/new")
async def new_external_withdrawal_form(
    request: Request,
    tank_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()
    return _external_form_response(
        request, tank=tank, form_entry_date=date.today().isoformat()
    )


@router.post("/tanks/{tank_id}/external/new")
async def create_external_withdrawal_post(
    request: Request,
    tank_id: int,
    amount_l: str = Form(""),
    entry_date: str = Form(""),
    recipient_name: str = Form(""),
    total_cost_eur: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    user=Depends(require_role(Role.contributor.value)),
):
    tank = tank_service.get_active_storage_tank_in_group(db, tank_id, group.id)
    if not tank:
        return not_found_response()

    def _error(msg: str):
        return _external_form_response(
            request,
            tank=tank,
            error=msg,
            form_amount_l=amount_l,
            form_entry_date=entry_date,
            form_recipient_name=recipient_name,
            form_total_cost_eur=total_cost_eur,
            form_notes=notes,
        )

    try:
        data = TankExternalWithdrawalCreate(
            amount_l=parse_float(amount_l, "Menge"),
            entry_date=parse_date(entry_date, "Datum"),
            recipient_name=recipient_name,
            total_cost_eur=parse_optional_float(total_cost_eur, "Kosten")
            if total_cost_eur.strip()
            else None,
            notes=notes.strip() or None,
        )
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _error(msg)

    try:
        ledger_service.post_external_withdrawal(db, user.id, group.id, tank, data)
    except ValueError as exc:
        return _error(str(exc))

    response = RedirectResponse(url=f"/tanks/{tank.id}", status_code=303)
    set_flash(response, "Externe Abgabe erfasst.", "success")
    return response


def _ledger_edit_form_response(
    request: Request,
    *,
    ledger,
    tank,
    error: str | None = None,
    blocked: bool = False,
    form_amount_l: str = "",
    form_entry_date: str = "",
    form_recipient_name: str = "",
    form_total_cost_eur: str = "",
    form_notes: str = "",
):
    return templates.TemplateResponse(
        request,
        "tank_ledger_edit_form.html",
        {
            "ledger": ledger,
            "tank": tank,
            "error": error,
            "blocked": blocked,
            "form_amount_l": form_amount_l,
            "form_entry_date": form_entry_date,
            "form_recipient_name": form_recipient_name,
            "form_total_cost_eur": form_total_cost_eur,
            "form_notes": form_notes,
        },
    )


@router.get("/tanks/ledger/{ledger_id}/edit")
async def edit_ledger_form(
    request: Request,
    ledger_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    ledger = ledger_service.get_active_ledger_entry_in_group(db, ledger_id, group.id)
    if not ledger:
        return not_found_response()
    tank = ledger.tank
    if ledger.movement_type == "vehicle_withdrawal":
        return _ledger_edit_form_response(
            request, ledger=ledger, tank=tank, blocked=True
        )
    amount_display = (
        str(abs(ledger.amount_l))
        if ledger.movement_type == "external_withdrawal"
        else str(ledger.amount_l)
    )
    return _ledger_edit_form_response(
        request,
        ledger=ledger,
        tank=tank,
        form_amount_l=amount_display,
        form_entry_date=ledger.entry_date.isoformat(),
        form_recipient_name=ledger.recipient_name or "",
        form_total_cost_eur=(
            str(ledger.total_cost_eur) if ledger.total_cost_eur is not None else ""
        ),
        form_notes=ledger.notes or "",
    )


@router.post("/tanks/ledger/{ledger_id}/edit")
async def edit_ledger_post(
    request: Request,
    ledger_id: int,
    amount_l: str = Form(""),
    entry_date: str = Form(""),
    recipient_name: str = Form(""),
    total_cost_eur: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.contributor.value)),
):
    ledger = ledger_service.get_active_ledger_entry_in_group(db, ledger_id, group.id)
    if not ledger:
        return not_found_response()
    tank = ledger.tank

    def _error(msg: str):
        return _ledger_edit_form_response(
            request,
            ledger=ledger,
            tank=tank,
            error=msg,
            form_amount_l=amount_l,
            form_entry_date=entry_date,
            form_recipient_name=recipient_name,
            form_total_cost_eur=total_cost_eur,
            form_notes=notes,
        )

    if ledger.movement_type == "vehicle_withdrawal":
        return _ledger_edit_form_response(
            request, ledger=ledger, tank=tank, blocked=True
        )

    try:
        if ledger.movement_type == "delivery":
            data = TankDeliveryCreate(
                amount_l=parse_float(amount_l, "Menge"),
                entry_date=parse_date(entry_date, "Datum"),
                total_cost_eur=parse_optional_float(total_cost_eur, "Kosten")
                if total_cost_eur.strip()
                else None,
                notes=notes.strip() or None,
            )
        elif ledger.movement_type == "external_withdrawal":
            data = TankExternalWithdrawalCreate(
                amount_l=parse_float(amount_l, "Menge"),
                entry_date=parse_date(entry_date, "Datum"),
                recipient_name=recipient_name,
                total_cost_eur=parse_optional_float(total_cost_eur, "Kosten")
                if total_cost_eur.strip()
                else None,
                notes=notes.strip() or None,
            )
        elif ledger.movement_type == "adjustment":
            data = TankAdjustmentCreate(
                amount_l=parse_float(amount_l, "Menge"),
                entry_date=parse_date(entry_date, "Datum"),
                notes=notes,
            )
        else:
            return _error("Unbekannte Bewegungsart.")
    except (ValueError, ValidationError) as exc:
        msg = (
            str(exc)
            if isinstance(exc, ValueError)
            else first_validation_error_message(exc)
        )
        return _error(msg)

    try:
        ledger_service.apply_ledger_entry_update(db, ledger, data)
    except ValueError as exc:
        return _error(str(exc))

    response = RedirectResponse(url=f"/tanks/{tank.id}", status_code=303)
    set_flash(response, "Bewegung aktualisiert.", "success")
    return response


@router.post("/tanks/ledger/{ledger_id}/delete")
async def delete_ledger_post(
    ledger_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    ledger = ledger_service.get_active_ledger_entry_in_group(db, ledger_id, group.id)
    if not ledger:
        return not_found_response()
    if ledger.movement_type == "vehicle_withdrawal":
        response = RedirectResponse(url=f"/tanks/{ledger.tank_id}", status_code=303)
        set_flash(
            response,
            "Fahrzeugentnahmen bitte über den Tankvorgang löschen.",
            "error",
        )
        return response
    tank_id = ledger.tank_id
    ledger_service.soft_delete_ledger_entry(db, ledger)
    response = RedirectResponse(url=f"/tanks/{tank_id}", status_code=303)
    set_flash(response, "Bewegung entfernt.", "success")
    return response
