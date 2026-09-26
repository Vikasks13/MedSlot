from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.booking import BookingStatus
from app.models.user import User
from app.schemas.booking import (
    BookingCreate,
    BookingResponse,
    PaginatedBookingsResponse,
)
from app.services.booking_service import BookingService

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Test Booking",
    description="Book a diagnostic test for an authenticated user at a chosen centre with future appointment time.",
)
async def create_booking(
    booking_in: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingResponse:
    """Create a diagnostic test booking in PENDING state."""
    booking = await BookingService.create_booking(
        db=db,
        user_id=current_user.id,
        booking_in=booking_in,
    )
    return BookingResponse.from_orm_with_context(booking)


@router.get(
    "",
    response_model=PaginatedBookingsResponse,
    status_code=status.HTTP_200_OK,
    summary="List User Bookings",
    description="Retrieve paginated list of bookings created by the authenticated user with optional status filter.",
)
async def list_bookings(
    status_filter: Optional[BookingStatus] = Query(None, alias="status", description="Filter by booking status"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=50, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedBookingsResponse:
    """List authenticated user's bookings."""
    bookings, total, total_pages = await BookingService.list_user_bookings(
        db=db,
        user_id=current_user.id,
        status_filter=status_filter,
        page=page,
        size=size,
    )
    items = [BookingResponse.from_orm_with_context(b) for b in bookings]
    return PaginatedBookingsResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        total_pages=total_pages,
    )


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Booking Details",
    description="Retrieve details of a specific booking. Users can only access their own bookings.",
)
async def get_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingResponse:
    """Get single booking by UUID."""
    booking = await BookingService.get_booking(
        db=db,
        booking_id=booking_id,
        current_user_id=current_user.id,
    )
    return BookingResponse.from_orm_with_context(booking)


@router.patch(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Booking",
    description="Cancel a PENDING or CONFIRMED booking. Already cancelled or failed bookings cannot be cancelled.",
)
async def cancel_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingResponse:
    """Cancel booking and transition status to CANCELLED."""
    booking = await BookingService.cancel_booking(
        db=db,
        booking_id=booking_id,
        current_user_id=current_user.id,
    )
    return BookingResponse.from_orm_with_context(booking)
