from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class DiagnosticTestBase(BaseModel):
    """Base fields for a diagnostic test."""
    name: str = Field(..., min_length=2, max_length=150, description="Test name")
    description: Optional[str] = Field(None, max_length=1000, description="Test details")
    price: Decimal = Field(
        ...,
        gt=Decimal("0.00"),
        decimal_places=2,
        description="Price in standard currency units (e.g. INR)",
        examples=[499.00],
    )


class DiagnosticTestCreate(DiagnosticTestBase):
    """Schema for adding a test to a centre."""
    pass


class DiagnosticTestResponse(DiagnosticTestBase):
    """Schema for returning diagnostic test information."""
    id: int
    centre_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
