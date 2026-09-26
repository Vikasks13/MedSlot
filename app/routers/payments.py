from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentWebhookPayload,
    PaymentWebhookResponse,
)
from app.services.payment_service import PaymentService
from app.utils.rate_limit import webhook_rate_limiter

settings = get_settings()
router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate Payment",
    description="Simulate payment processing for a booking. Transitions booking status to CONFIRMED or FAILED.",
)
async def process_payment(
    payment_in: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    """Process simulated payment for an authenticated user's booking."""
    payment, booking = await PaymentService.process_simulated_payment(
        db=db,
        current_user_id=current_user.id,
        payment_in=payment_in,
    )
    return PaymentResponse(
        id=payment.id,
        booking_id=payment.booking_id,
        amount=payment.amount,
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        payment_method=payment.payment_method,
        failure_reason=payment.failure_reason,
        created_at=payment.created_at,
        booking_status=booking.status,
    )


@router.post(
    "/webhook",
    response_model=PaymentWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Payment Provider Webhook (Idempotent)",
    description=(
        "Receives payment status updates from external/simulated payment providers. "
        "Strictly idempotent: repeated deliveries of the same event_id return HTTP 200 "
        "without corrupting state or creating duplicate records."
    ),
    dependencies=[Depends(webhook_rate_limiter)],
)
async def payment_webhook(
    payload: PaymentWebhookPayload,
    db: AsyncSession = Depends(get_db),
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
) -> PaymentWebhookResponse:
    """
    Handle incoming payment webhook notification.
    Idempotent by event_id.
    """
    # Optional webhook secret verification if configured and passed
    if x_webhook_secret and x_webhook_secret != settings.PAYMENT_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret header.",
        )

    res_status, message, payment_id, booking_status = (
        await PaymentService.process_webhook_event(db=db, payload=payload)
    )

    return PaymentWebhookResponse(
        status=res_status,
        message=message,
        event_id=payload.event_id,
        payment_id=payment_id,
        booking_status=booking_status,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Payment Details",
    description="Retrieve details of a specific payment by ID. Requires authentication and booking ownership.",
)
async def get_payment(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentResponse:
    """Get single payment by ID."""
    payment = await PaymentService.get_payment_by_id(
        db=db,
        payment_id=payment_id,
        current_user_id=current_user.id,
    )
    return PaymentResponse(
        id=payment.id,
        booking_id=payment.booking_id,
        amount=payment.amount,
        status=payment.status,
        idempotency_key=payment.idempotency_key,
        payment_method=payment.payment_method,
        failure_reason=payment.failure_reason,
        created_at=payment.created_at,
        booking_status=payment.booking.status if payment.booking else None,
    )
