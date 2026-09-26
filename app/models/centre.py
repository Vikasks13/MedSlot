from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DiagnosticCentre(Base):
    """Diagnostic Centre offering clinical and pathology tests."""

    __tablename__ = "diagnostic_centres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    location: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    contact_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

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

    # One-to-many relationship with DiagnosticTest
    tests: Mapped[List["DiagnosticTest"]] = relationship(
        "DiagnosticTest",
        back_populates="centre",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DiagnosticCentre id={self.id} name='{self.name}' location='{self.location}'>"
