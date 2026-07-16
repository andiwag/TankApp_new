from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_entitlement
from app.models import Group
from app.services import export as export_service

router = APIRouter()


@router.get("/export/fuel-entries.csv")
async def export_fuel_entries_csv(
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("export")),
):
    content = export_service.fuel_entries_csv(db, group.id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="fuel-entries.csv"',
        },
    )


@router.get("/export/vehicles.csv")
async def export_vehicles_csv(
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("export")),
):
    content = export_service.vehicles_csv(db, group.id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="vehicles.csv"',
        },
    )
