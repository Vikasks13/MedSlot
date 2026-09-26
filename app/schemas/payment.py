from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus
from app.models.payment import PaymentStatus


class PaymentCreate(BaseModel):
    """Payload to simulate a payment for an existing booking."""
    booking_id: str = Field(..., description="UUID of the booking to pay for")
    payment_method: Optional[str] = Field("UPI", description="Payment method (e.g., UPI, CARD, NET_BANKING)")
    simulate_status: Optional[PaymentStatus] = Field(
        None,
        description="Optional forced status for deterministic testing. If omitted, simulated with 80% success rate.",
    )


class PaymentResponse(BaseModel):
    """Response returned upon payment processing."""
    id: str
    booking_id: str
    amount: Decimal
    status: PaymentStatus
    idempotency_key: str
    payment_method: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    booking_status: BookingStatus

    model_config = ConfigDict(from_attributes=True)


class PaymentWebhookPayload(BaseModel):
    """Payload sent by the simulated payment provider to the webhook."""
    event_id: str = Field(
        ...,
        min_length=4,
        max_length=150,
        description="Unique event ID from provider (acts as the idempotency key)",
        examples=["evt_sim_9876543210"],
    )
    event_type: str = Field(
        "payment.processed",
        description="Event type name",
        examples=["payment.succeeded", "payment.failed"],
    )
    booking_id: str = Field(..., description="Target booking UUID")
    amount: Decimal = Field(..., gt=0, description="Payment amount")
    status: PaymentStatus = Field(..., description="Payment outcome: SUCCESS or FAILED")
    payment_method: Optional[str] = Field("WEBHOOK_GATEWAY", description="Payment rail")
    failure_reason: Optional[str] = Field(None, description="Reason if payment status is FAILED")


class PaymentWebhookResponse(BaseModel):
    """Acknowledgement response returned to the payment provider."""
    status: str = Field(..., description="'processed' or 'already_processed'")
    message: str
    event_id: str
    payment_id: Optional[str] = None
    booking_status: Optional[str] = None
