from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.test import DiagnosticTestResponse


class DiagnosticCentreBase(BaseModel):
    """Base fields for a diagnostic centre."""
    name: str = Field(..., min_length=2, max_length=150, description="Centre name")
    location: str = Field(..., min_length=2, max_length=255, description="Physical address / city")
    contact_number: Optional[str] = Field(None, max_length=30, description="Phone or contact info")


class DiagnosticCentreCreate(DiagnosticCentreBase):
    """Schema for registering a new diagnostic centre."""
    pass


class DiagnosticCentreResponse(DiagnosticCentreBase):
    """Schema for returning diagnostic centre with nested tests."""
    id: int
    created_at: datetime
    tests: List[DiagnosticTestResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaginatedCentresResponse(BaseModel):
    """Pagination envelope for diagnostic centres list."""
    items: List[DiagnosticCentreResponse]
    total: int
    page: int
    size: int
    total_pages: int
