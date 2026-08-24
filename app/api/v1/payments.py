from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.billing import Payment
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    RefundRequest,
    RefundResponse,
)
from app.services.billing_service import (
    apply_payment_notification,
    create_payment_intent,
    sync_user_role,
)
from app.services.payments import PaymentOutcome, PaymentProviderError, get_provider

router = APIRouter(prefix="/payments", tags=["payments"])


def _plan_amount(plan: str) -> int:
    amount = settings.pro_price_idr if plan == "pro" else settings.max_price_idr
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Plan pricing is not configured"
        )
    return amount


@router.get("/config")
def payment_config(current_user=Depends(get_current_user)):
    """Non-secret settings the checkout UI needs, shaped by the active provider."""
    try:
        return get_provider().client_config()
    except PaymentProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.post("/create", response_model=PaymentCreateResponse)
@limiter.limit("5/minute")
def create_payment(
    request: Request,
    payload: PaymentCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    provider = get_provider()
    payment = create_payment_intent(
        db,
        user_id=current_user.id,
        plan=payload.plan,
        amount=_plan_amount(payload.plan),
        provider=provider.name,
    )
    try:
        session = provider.create_checkout(
            order_id=payment.provider_order_id,
            amount=payment.amount,
            currency=payment.currency,
            customer_email=current_user.email,
            item_name=f"VeloraAi {payload.plan.upper()}",
        )
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    payment.checkout_token = session.token
    db.commit()
    return PaymentCreateResponse(
        order_id=session.order_id,
        amount=session.amount,
        currency=session.currency,
        checkout_token=session.token,
        redirect_url=session.redirect_url,
    )


@router.post("/notification", status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_webhook)
def payment_notification(request: Request, payload: dict, db: Session = Depends(get_db)):
    """Provider webhook.

    Defence in depth, in order: the provider authenticates the body, the amount
    is matched against what we recorded, and the transaction is then re-fetched
    from the provider. A forged notification cannot grant a plan even if the
    signature scheme itself were broken.
    """
    provider = get_provider()

    try:
        envelope = provider.parse_notification(payload)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    payment = (
        db.query(Payment)
        .filter(
            Payment.provider == provider.name,
            Payment.provider_order_id == envelope.order_id,
        )
        .first()
    )
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if envelope.gross_amount is not None and str(payment.amount) != envelope.gross_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount mismatch"
        )
    if not envelope.signature_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid payment signature"
        )

    try:
        verified = provider.fetch_transaction(envelope.order_id)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if verified.order_id != envelope.order_id or (
        envelope.gross_amount is not None and verified.gross_amount != envelope.gross_amount
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Verified payment mismatch"
        )

    updated = apply_payment_notification(
        db,
        provider=provider.name,
        provider_order_id=verified.order_id,
        provider_transaction_id=verified.transaction_id,
        transaction_status=verified.raw_status,
        outcome=verified.outcome,
        payment_type=verified.payment_type,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return {"status": "ok"}


@router.post(
    "/{payment_id}/refund",
    response_model=RefundResponse,
    dependencies=[Depends(require_roles("admin"))],
)
@limiter.limit("10/minute")
def refund_payment(
    request: Request,
    payment_id: int,
    payload: RefundRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Refund a settled payment, in full or in part.

    Partial refunds are driven by the amount already returned rather than by the
    provider's refund status. Keying off the status meant the first partial
    refund marked the payment as refunded, and every later call was rejected as
    a duplicate even though money was still outstanding.
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    try:
        provider = get_provider(payment.provider)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not provider.supports_refund:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{provider.name} refunds are handled outside VeloraAi",
        )
    if payment.status not in {"settlement", "partially_refunded"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only settled payments can be refunded"
        )

    already_refunded = payment.refund_amount or 0
    remaining = payment.amount - already_refunded
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Payment has already been fully refunded"
        )

    requested = payload.amount if payload and payload.amount is not None else remaining
    if requested > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Refund exceeds the outstanding amount ({remaining})",
        )

    reason = (payload.reason if payload else None) or "VeloraAi admin refund"
    try:
        result = provider.refund(
            order_id=payment.provider_order_id,
            amount=requested,
            reason=reason,
        )
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    payment.refund_status = result.raw_status
    payment.refund_transaction_id = result.reference

    if result.outcome is PaymentOutcome.REFUNDED:
        # Trust what the provider says it moved, not what we asked for.
        settled_amount = result.amount if result.amount > 0 else requested
        payment.refund_amount = already_refunded + settled_amount
        fully_refunded = payment.refund_amount >= payment.amount
        if fully_refunded:
            payment.refunded_at = payment.refunded_at or datetime.now(UTC)
            payment.status = "refunded"
            # Entitlement only ends when the customer got all their money back.
            # A partial refund - a pro-rata adjustment, say - must not cancel a
            # subscription the customer is still paying for.
            if payment.subscription is not None:
                payment.subscription.status = "canceled"
            sync_user_role(db, user_id=payment.user_id)
        else:
            payment.status = "partially_refunded"
    else:
        # The provider has not settled it; record nothing as returned yet.
        settled_amount = 0
        fully_refunded = False

    db.commit()
    db.refresh(payment)

    refunded_total = payment.refund_amount or 0
    return RefundResponse(
        status=payment.refund_status or "pending",
        payment_id=payment.id,
        refund_amount=settled_amount,
        refunded_total=refunded_total,
        remaining=payment.amount - refunded_total,
        fully_refunded=fully_refunded,
    )
