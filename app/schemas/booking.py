from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    """Schema for booking a diagnostic test."""
    centre_id: int = Field(..., description="ID of diagnostic centre")
    test_id: int = Field(..., description="ID of diagnostic test to book")
    appointment_date_time: datetime = Field(
        ...,
        description="Scheduled appointment date & time (must be in the future)",
    )
    notes: Optional[str] = Field(None, max_length=500, description="Optional medical or access notes")

    @field_validator("appointment_date_time")
    @classmethod
    def validate_future_date(cls, v: datetime) -> datetime:
        # Normalize timezone for comparison
        now = datetime.now(timezone.utc)
        target = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if target <= now:
            raise ValueError("Appointment date and time must be in the future.")
        return target


class BookingResponse(BaseModel):
    """Schema for returning booking details."""
    id: str
    user_id: int
    centre_id: int
    test_id: int
    appointment_date_time: datetime
    amount: Decimal
    status: BookingStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Additional contextual fields for convenient UI display
    patient_name: Optional[str] = None
    centre_name: Optional[str] = None
    test_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_context(cls, booking) -> "BookingResponse":
        return cls(
            id=booking.id,
            user_id=booking.user_id,
            centre_id=booking.centre_id,
            test_id=booking.test_id,
            appointment_date_time=booking.appointment_date_time,
            amount=booking.amount,
            status=booking.status,
            notes=booking.notes,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
            patient_name=booking.user.name if booking.user else None,
            centre_name=booking.centre.name if booking.centre else None,
            test_name=booking.test.name if booking.test else None,
        )


class PaginatedBookingsResponse(BaseModel):
    """Paginated list of bookings."""
    items: List[BookingResponse]
    total: int
    page: int
    size: int
    total_pages: int
