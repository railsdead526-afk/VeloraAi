from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.billing import Payment
from app.schemas.payment import PaymentCreateRequest, PaymentCreateResponse
from app.services.billing_service import apply_payment_notification, create_payment_intent
from app.services.midtrans_service import MidtransError, MidtransService

router = APIRouter(prefix="/payments", tags=["payments"])
CHECKOUT_FILE = Path(__file__).resolve().parents[2] / "static" / "checkout.html"


def _plan_amount(plan: str) -> int:
    amount = settings.pro_price_idr if plan == "pro" else settings.max_price_idr
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Plan pricing is not configured")
    return amount


@router.get("/checkout", include_in_schema=False)
def checkout_page():
    return FileResponse(CHECKOUT_FILE)


@router.get("/config")
def payment_config(current_user=Depends(get_current_user)):
    if not settings.midtrans_client_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Payment client is not configured")
    return {
        "provider": "midtrans",
        "is_production": settings.midtrans_is_production,
        "pro_price_idr": settings.pro_price_idr,
        "max_price_idr": settings.max_price_idr,
    }


@router.get("/snap-script.js", include_in_schema=False)
def snap_script():
    client_key = settings.midtrans_client_key
    if not client_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Payment client is not configured")
    origin = "https://app.midtrans.com" if settings.midtrans_is_production else "https://app.sandbox.midtrans.com"
    body = f"document.write('<script src=\\\"{origin}/snap/snap.js\\\" data-client-key=\\\"{client_key}\\\"><\\/script>');"
    return Response(content=body, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@router.post("/create", response_model=PaymentCreateResponse)
@limiter.limit("5/minute")
def create_payment(
    request: Request,
    payload: PaymentCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    payment = create_payment_intent(
        db,
        user_id=current_user.id,
        plan=payload.plan,
        amount=_plan_amount(payload.plan),
        provider="midtrans",
    )
    try:
        result = MidtransService().create_snap_transaction(
            order_id=payment.provider_order_id,
            gross_amount=payment.amount,
            customer_email=current_user.email,
            item_name=f"VeloraAi {payload.plan.upper()}",
        )
    except MidtransError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    payment.snap_token = result["token"]
    db.commit()
    return PaymentCreateResponse(
        order_id=payment.provider_order_id,
        amount=payment.amount,
        currency=payment.currency,
        snap_token=result["token"],
        redirect_url=result["redirect_url"],
    )


@router.post("/notification", status_code=status.HTTP_200_OK)
def payment_notification(payload: dict, db: Session = Depends(get_db)):
    order_id = str(payload.get("order_id", "")).strip()
    status_code = str(payload.get("status_code", "")).strip()
    gross_amount = str(payload.get("gross_amount", "")).strip()
    signature_key = str(payload.get("signature_key", "")).strip()
    if not order_id or not status_code or not gross_amount or not signature_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notification payload")

    payment = db.query(Payment).filter(Payment.provider == "midtrans", Payment.provider_order_id == order_id).first()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if str(payment.amount) != gross_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount mismatch")

    try:
        midtrans = MidtransService()
        if not midtrans.verify_notification_signature(
            order_id=order_id,
            status_code=status_code,
            gross_amount=gross_amount,
            signature_key=signature_key,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid payment signature")
        verified = midtrans.get_transaction_status(order_id)
    except MidtransError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if str(verified.get("order_id", "")) != order_id or str(verified.get("gross_amount", "")) != gross_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verified payment mismatch")

    updated = apply_payment_notification(
        db,
        provider="midtrans",
        provider_order_id=order_id,
        provider_transaction_id=verified.get("transaction_id"),
        transaction_status=str(verified.get("transaction_status", "")),
        payment_type=verified.get("payment_type"),
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return {"status": "ok"}


@router.post("/{payment_id}/refund", dependencies=[Depends(require_roles("admin"))])
@limiter.limit("10/minute")
def refund_payment(
    request: Request,
    payment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if payment.provider != "midtrans":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported payment provider")
    if payment.status != "settlement":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only settled payments can be refunded")
    if payment.refund_status in {"settlement", "200"}:
        return {"status": "already_refunded", "payment_id": payment.id, "refund_amount": payment.refund_amount}

    refund_amount = payment.amount - payment.refund_amount
    if refund_amount <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has already been fully refunded")
    try:
        result = MidtransService().refund_transaction(payment.provider_order_id, refund_amount, "VeloraAi admin refund")
    except MidtransError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    payment.refund_amount = refund_amount
    payment.refund_status = str(result.get("status_code", result.get("status", "pending")))
    payment.refund_transaction_id = result.get("refund_key") or result.get("transaction_id")
    if payment.refund_status in {"settlement", "200"}:
        payment.refunded_at = payment.refunded_at or datetime.now(timezone.utc)
        payment.status = "refunded"
        if payment.subscription is not None:
            payment.subscription.status = "canceled"
    db.commit()
    return {"status": payment.refund_status, "payment_id": payment.id, "refund_amount": refund_amount}
