from datetime import datetime
from decimal import Decimal
import enum
from typing import Optional
import uuid
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Booking(Base):
    """Diagnostic test booking made by a patient/user."""

    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    centre_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("diagnostic_centres.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    test_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("diagnostic_tests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    appointment_date_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status_enum", native_enum=False),
        default=BookingStatus.PENDING,
        nullable=False,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", lazy="joined")
    centre = relationship("DiagnosticCentre", lazy="joined")
    test = relationship("DiagnosticTest", lazy="joined")

    def __repr__(self) -> str:
        return f"<Booking id={self.id} user_id={self.user_id} test_id={self.test_id} status={self.status.value}>"
