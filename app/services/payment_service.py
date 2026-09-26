import random
from typing import Optional, Tuple
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate, PaymentWebhookPayload


class PaymentService:
    """Service handling simulated payments and idempotent webhook processing."""

    @staticmethod
    async def process_simulated_payment(
        db: AsyncSession,
        current_user_id: int,
        payment_in: PaymentCreate,
    ) -> Tuple[Payment, Booking]:
        """
        Simulate payment processing for a booking.
        Validates:
        1. Booking exists (404).
        2. Booking belongs to current user (403).
        3. Booking is not CANCELLED or already CONFIRMED (400).
        Creates payment record and transitions booking state.
        """
        # Fetch booking with eager loaded relationships
        booking_query = (
            select(Booking)
            .where(Booking.id == payment_in.booking_id)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.centre),
                selectinload(Booking.test),
            )
        )
        result = await db.execute(booking_query)
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID '{payment_in.booking_id}' not found.",
            )

        if booking.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to pay for this booking.",
            )

        if booking.status == BookingStatus.CONFIRMED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This booking has already been paid for and is CONFIRMED.",
            )

        if booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot make payment for a CANCELLED booking.",
            )

        # Determine outcome: either explicit simulate_status or default 80% success
        if payment_in.simulate_status:
            payment_status = payment_in.simulate_status
        else:
            payment_status = (
                PaymentStatus.SUCCESS if random.random() < 0.80 else PaymentStatus.FAILED
            )

        failure_reason = None
        if payment_status == PaymentStatus.FAILED:
            failure_reason = "Simulated card transaction declined by issuing bank."

        idempotency_key = f"sim_pay_{booking.id}_{uuid.uuid4().hex[:12]}"

        payment = Payment(
            booking_id=booking.id,
            idempotency_key=idempotency_key,
            provider_event_id=f"evt_{uuid.uuid4().hex[:16]}",
            amount=booking.amount,
            status=payment_status,
            payment_method=payment_in.payment_method or "UPI",
            failure_reason=failure_reason,
        )
        db.add(payment)

        # Update booking state based on payment result
        if payment_status == PaymentStatus.SUCCESS:
            booking.status = BookingStatus.CONFIRMED
        else:
            booking.status = BookingStatus.FAILED

        await db.flush()
        await db.refresh(payment)
        return payment, booking

    @staticmethod
    async def process_webhook_event(
        db: AsyncSession,
        payload: PaymentWebhookPayload,
    ) -> Tuple[str, str, Optional[str], Optional[str]]:
        """
        Idempotent payment webhook event processor.
        Guarantees:
        1. Repeated webhook deliveries return HTTP 200 without creating duplicate payments.
        2. Booking state is never corrupted by repeated events.
        3. Race conditions handled by DB unique index on idempotency_key.
        Returns: (status, message, payment_id, booking_status)
        """
        # Step 1: Idempotency check via idempotency_key / event_id
        existing_query = (
            select(Payment)
            .where(Payment.idempotency_key == payload.event_id)
            .options(selectinload(Payment.booking))
        )
        existing_res = await db.execute(existing_query)
        existing_payment = existing_res.scalar_one_or_none()

        if existing_payment:
            booking_status = (
                existing_payment.booking.status.value
                if existing_payment.booking
                else None
            )
            return (
                "already_processed",
                "Webhook event already processed previously. No changes made (idempotent).",
                existing_payment.id,
                booking_status,
            )

        # Step 2: Validate target booking exists
        booking_query = (
            select(Booking)
            .where(Booking.id == payload.booking_id)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.centre),
                selectinload(Booking.test),
            )
        )
        booking_res = await db.execute(booking_query)
        booking = booking_res.scalar_one_or_none()
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target booking with ID '{payload.booking_id}' not found.",
            )

        # Step 3: Create payment record
        new_payment = Payment(
            booking_id=booking.id,
            idempotency_key=payload.event_id,
            provider_event_id=payload.event_id,
            amount=payload.amount,
            status=payload.status,
            payment_method=payload.payment_method or "WEBHOOK_GATEWAY",
            failure_reason=payload.failure_reason,
        )
        db.add(new_payment)

        # Step 4: Update booking status safely
        if payload.status == PaymentStatus.SUCCESS:
            # Only update if booking is not CANCELLED
            if booking.status != BookingStatus.CANCELLED:
                booking.status = BookingStatus.CONFIRMED
        elif payload.status == PaymentStatus.FAILED:
            # Only transition to FAILED if currently PENDING
            if booking.status == BookingStatus.PENDING:
                booking.status = BookingStatus.FAILED

        # Step 5: Flush with atomic integrity guard against concurrent duplicate events
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # Concurrently inserted event_id
            concurrent_res = await db.execute(
                select(Payment).where(Payment.idempotency_key == payload.event_id)
            )
            concurrent_p = concurrent_res.scalar_one_or_none()
            return (
                "already_processed",
                "Webhook event processed concurrently by another worker (idempotent).",
                concurrent_p.id if concurrent_p else None,
                booking.status.value,
            )

        await db.refresh(new_payment)
        return (
            "processed",
            "Payment webhook successfully applied.",
            new_payment.id,
            booking.status.value,
        )

    @staticmethod
    async def get_payment_by_id(
        db: AsyncSession,
        payment_id: str,
        current_user_id: int,
    ) -> Payment:
        """Fetch payment by ID with ownership verification through linked booking."""
        query = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(selectinload(Payment.booking))
        )
        result = await db.execute(query)
        payment = result.scalar_one_or_none()
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment with ID '{payment_id}' not found.",
            )

        if payment.booking and payment.booking.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this payment.",
            )

        return payment
