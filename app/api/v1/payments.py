from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.billing import Payment
from app.schemas.payment import PaymentCreateRequest, PaymentCreateResponse
from app.services.billing_service import apply_payment_notification, create_payment_intent
from app.services.midtrans_service import MidtransError, MidtransService

router = APIRouter(prefix="/payments", tags=["payments"])


def _plan_amount(plan: str) -> int:
    amount = settings.pro_price_idr if plan == "pro" else settings.max_price_idr
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plan pricing is not configured",
        )
    return amount


@router.post("/create", response_model=PaymentCreateResponse)
@limiter.limit("5/minute")
def create_payment(
    request: Request,
    payload: PaymentCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    amount = _plan_amount(payload.plan)
    payment = create_payment_intent(
        db,
        user_id=current_user.id,
        plan=payload.plan,
        amount=amount,
        provider="midtrans",
    )

    try:
        midtrans = MidtransService()
        result = midtrans.create_snap_transaction(
            order_id=payment.provider_order_id,
            gross_amount=payment.amount,
            customer_email=current_user.email,
            item_name=f"VeloraAi {payload.plan.upper()}",
        )
    except MidtransError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

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

    payment = (
        db.query(Payment)
        .filter(Payment.provider == "midtrans", Payment.provider_order_id == order_id)
        .first()
    )
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if str(payment.amount) != gross_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount mismatch")

    try:
        midtrans = MidtransService()
    except MidtransError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not midtrans.verify_notification_signature(
        order_id=order_id,
        status_code=status_code,
        gross_amount=gross_amount,
        signature_key=signature_key,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid payment signature")

    try:
        verified = midtrans.get_transaction_status(order_id)
    except MidtransError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if str(verified.get("order_id", "")) != order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verified order mismatch")
    if str(verified.get("gross_amount", "")) != gross_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verified amount mismatch")

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
