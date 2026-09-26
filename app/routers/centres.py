from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.centre import DiagnosticCentre
from app.models.test import DiagnosticTest
from app.models.user import User
from app.schemas.centre import (
    DiagnosticCentreCreate,
    DiagnosticCentreResponse,
    PaginatedCentresResponse,
)
from app.schemas.test import DiagnosticTestCreate, DiagnosticTestResponse
from app.services.centre_service import CentreService

router = APIRouter(tags=["Diagnostic Centres & Tests"])


@router.get(
    "/centres",
    response_model=PaginatedCentresResponse,
    status_code=status.HTTP_200_OK,
    summary="List Diagnostic Centres",
    description="Retrieve paginated diagnostic centres with available tests and optional location/name filters.",
)
async def list_centres(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    location: Optional[str] = Query(None, description="Filter by location substring"),
    search: Optional[str] = Query(None, description="Search by centre name substring"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedCentresResponse:
    """List centres with pagination and filters."""
    items, total, total_pages = await CentreService.list_centres(
        db, page=page, size=size, location=location, search=search
    )
    return PaginatedCentresResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        total_pages=total_pages,
    )


@router.post(
    "/centres",
    response_model=DiagnosticCentreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Diagnostic Centre",
    description="Register a new diagnostic centre (requires authenticated user).",
)
async def create_centre(
    centre_in: DiagnosticCentreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiagnosticCentre:
    """Create a new diagnostic centre."""
    return await CentreService.create_centre(db, centre_in)


@router.get(
    "/centres/{centre_id}",
    response_model=DiagnosticCentreResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Diagnostic Centre Details",
    description="Retrieve a diagnostic centre by ID along with its list of offered tests.",
)
async def get_centre(
    centre_id: int,
    db: AsyncSession = Depends(get_db),
) -> DiagnosticCentre:
    """Get single centre by ID."""
    return await CentreService.get_centre_by_id(db, centre_id)


@router.get(
    "/centres/{centre_id}/tests",
    response_model=List[DiagnosticTestResponse],
    status_code=status.HTTP_200_OK,
    summary="List Tests for Centre",
    description="Retrieve all diagnostic tests available at a specific centre.",
)
async def list_centre_tests(
    centre_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[DiagnosticTest]:
    """List tests for a given centre."""
    return await CentreService.list_tests_for_centre(db, centre_id)


@router.post(
    "/centres/{centre_id}/tests",
    response_model=DiagnosticTestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Test to Centre",
    description="Add a new diagnostic test and price to an existing centre (requires authenticated user).",
)
async def add_test_to_centre(
    centre_id: int,
    test_in: DiagnosticTestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiagnosticTest:
    """Add a test to a centre."""
    return await CentreService.add_test_to_centre(db, centre_id, test_in)


@router.get(
    "/tests/{test_id}",
    response_model=DiagnosticTestResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Diagnostic Test Details",
    description="Retrieve specific diagnostic test details by test ID.",
)
async def get_test(
    test_id: int,
    db: AsyncSession = Depends(get_db),
) -> DiagnosticTest:
    """Get single test by ID."""
    return await CentreService.get_test_by_id(db, test_id)
