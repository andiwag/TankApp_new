"""Stripe webhook endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.billing.notifications import notify_group_payment_failed
from app.services.billing.webhooks import process_stripe_webhook

router = APIRouter()


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        notify_group_id = process_stripe_webhook(db, payload, sig_header)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if notify_group_id is not None:
        await notify_group_payment_failed(db, notify_group_id)
    return {"received": True}
