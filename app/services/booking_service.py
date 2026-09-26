from math import ceil
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.centre import DiagnosticCentre
from app.models.test import DiagnosticTest
from app.schemas.booking import BookingCreate


class BookingService:
    """Business logic for diagnostic test bookings, status lifecycle, and authorization."""

    @staticmethod
    async def create_booking(
        db: AsyncSession,
        user_id: int,
        booking_in: BookingCreate,
    ) -> Booking:
        """
        Create a new test booking.
        Validates:
        1. Diagnostic centre exists (404).
        2. Diagnostic test exists (404).
        3. Test belongs to the specified centre (400).
        Copies price snapshot into booking.amount.
        Sets initial status to PENDING.
        """
        # 1. Verify centre exists
        centre_res = await db.execute(
            select(DiagnosticCentre).where(DiagnosticCentre.id == booking_in.centre_id)
        )
        centre = centre_res.scalar_one_or_none()
        if not centre:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Diagnostic centre with ID {booking_in.centre_id} not found.",
            )

        # 2. Verify test exists
        test_res = await db.execute(
            select(DiagnosticTest).where(DiagnosticTest.id == booking_in.test_id)
        )
        test = test_res.scalar_one_or_none()
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Diagnostic test with ID {booking_in.test_id} not found.",
            )

        # 3. Verify test belongs to the centre
        if test.centre_id != booking_in.centre_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Test '{test.name}' (ID {test.id}) is not offered by "
                    f"centre '{centre.name}' (ID {centre.id})."
                ),
            )

        # 4. Create booking snapshotting the test price
        booking = Booking(
            user_id=user_id,
            centre_id=booking_in.centre_id,
            test_id=booking_in.test_id,
            appointment_date_time=booking_in.appointment_date_time,
            amount=test.price,
            status=BookingStatus.PENDING,
            notes=booking_in.notes.strip() if booking_in.notes else None,
        )
        db.add(booking)
        await db.flush()
        return await BookingService.get_booking(db, booking.id, user_id)

    @staticmethod
    async def get_booking(
        db: AsyncSession,
        booking_id: str,
        current_user_id: int,
    ) -> Booking:
        """
        Retrieve booking by ID with ownership verification.
        Raises 404 if not found.
        Raises 403 if booking belongs to a different user.
        """
        query = (
            select(Booking)
            .where(Booking.id == booking_id)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.centre),
                selectinload(Booking.test),
            )
        )
        result = await db.execute(query)
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID '{booking_id}' not found.",
            )

        if booking.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view or manage this booking.",
            )

        return booking

    @staticmethod
    async def list_user_bookings(
        db: AsyncSession,
        user_id: int,
        status_filter: Optional[BookingStatus] = None,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[Booking], int, int]:
        """
        List bookings for the authenticated user with pagination and optional status filter.
        Returns: (bookings, total_count, total_pages)
        """
        conditions = [Booking.user_id == user_id]
        if status_filter:
            conditions.append(Booking.status == status_filter)

        # Count total
        count_query = select(func.count(Booking.id)).where(*conditions)
        total_res = await db.execute(count_query)
        total = total_res.scalar_one()

        if total == 0:
            return [], 0, 0

        total_pages = ceil(total / size)
        offset = (page - 1) * size

        query = (
            select(Booking)
            .where(*conditions)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.centre),
                selectinload(Booking.test),
            )
            .order_by(Booking.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await db.execute(query)
        bookings = list(result.scalars().all())
        return bookings, total, total_pages

    @classmethod
    async def cancel_booking(
        cls,
        db: AsyncSession,
        booking_id: str,
        current_user_id: int,
    ) -> Booking:
        """
        Cancel a booking.
        Enforces state transition rules:
        - PENDING -> CANCELLED (allowed)
        - CONFIRMED -> CANCELLED (allowed)
        - CANCELLED -> error (already cancelled)
        - FAILED -> error (cannot cancel failed)
        """
        booking = await BookingService.get_booking(db, booking_id, current_user_id)

        if booking.status == BookingStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This booking is already cancelled.",
            )

        if booking.status == BookingStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel a booking that has already failed.",
            )

        booking.status = BookingStatus.CANCELLED
        await db.flush()
        return await BookingService.get_booking(db, booking_id, current_user_id)
