from math import ceil
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.centre import DiagnosticCentre
from app.models.test import DiagnosticTest
from app.schemas.centre import DiagnosticCentreCreate
from app.schemas.test import DiagnosticTestCreate
from app.utils.cache import CacheService


class CentreService:
    """Business logic for diagnostic centres and test offerings."""

    @staticmethod
    async def get_centre_by_id(db: AsyncSession, centre_id: int) -> DiagnosticCentre:
        """Fetch a centre by ID or raise HTTP 404."""
        query = (
            select(DiagnosticCentre)
            .where(DiagnosticCentre.id == centre_id)
            .options(selectinload(DiagnosticCentre.tests))
        )
        result = await db.execute(query)
        centre = result.scalar_one_or_none()
        if not centre:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Diagnostic centre with ID {centre_id} not found.",
            )
        return centre

    @staticmethod
    async def list_centres(
        db: AsyncSession,
        page: int = 1,
        size: int = 10,
        location: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[DiagnosticCentre], int, int]:
        """
        List diagnostic centres with pagination and optional filtering.
        Returns: (items, total_count, total_pages)
        """
        # Base filter conditions
        conditions = []
        if location:
            conditions.append(DiagnosticCentre.location.ilike(f"%{location.strip()}%"))
        if search:
            conditions.append(DiagnosticCentre.name.ilike(f"%{search.strip()}%"))

        # Count total items
        count_query = select(func.count(DiagnosticCentre.id))
        if conditions:
            count_query = count_query.where(*conditions)
        total_res = await db.execute(count_query)
        total = total_res.scalar_one()

        if total == 0:
            return [], 0, 0

        total_pages = ceil(total / size)
        offset = (page - 1) * size

        # Fetch paginated rows with tests eager loaded
        query = (
            select(DiagnosticCentre)
            .options(selectinload(DiagnosticCentre.tests))
            .order_by(DiagnosticCentre.id.asc())
            .offset(offset)
            .limit(size)
        )
        if conditions:
            query = query.where(*conditions)

        result = await db.execute(query)
        centres = list(result.scalars().all())
        return centres, total, total_pages

    @staticmethod
    async def create_centre(
        db: AsyncSession, centre_in: DiagnosticCentreCreate
    ) -> DiagnosticCentre:
        """Create a new diagnostic centre."""
        centre = DiagnosticCentre(
            name=centre_in.name.strip(),
            location=centre_in.location.strip(),
            contact_number=centre_in.contact_number.strip() if centre_in.contact_number else None,
        )
        db.add(centre)
        await db.flush()
        await db.refresh(centre, attribute_names=["tests"])
        await CacheService.clear_pattern("centres:")
        return centre

    @classmethod
    async def list_tests_for_centre(
        cls, db: AsyncSession, centre_id: int
    ) -> List[DiagnosticTest]:
        """List all diagnostic tests offered by a centre."""
        # Ensure centre exists first
        await cls.get_centre_by_id(db, centre_id)

        query = (
            select(DiagnosticTest)
            .where(DiagnosticTest.centre_id == centre_id)
            .order_by(DiagnosticTest.name.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def add_test_to_centre(
        cls, db: AsyncSession, centre_id: int, test_in: DiagnosticTestCreate
    ) -> DiagnosticTest:
        """
        Add a diagnostic test to a centre.
        Raises HTTP 404 if centre does not exist.
        Raises HTTP 409 if a test with the same name already exists in this centre.
        """
        # Ensure centre exists
        await cls.get_centre_by_id(db, centre_id)

        # Check for duplicate test name within the same centre
        dup_query = select(DiagnosticTest).where(
            DiagnosticTest.centre_id == centre_id,
            func.lower(DiagnosticTest.name) == test_in.name.strip().lower(),
        )
        dup_result = await db.execute(dup_query)
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A test named '{test_in.name}' already exists at this centre.",
            )

        test = DiagnosticTest(
            centre_id=centre_id,
            name=test_in.name.strip(),
            description=test_in.description.strip() if test_in.description else None,
            price=test_in.price,
        )
        db.add(test)
        await db.flush()
        await db.refresh(test)
        await CacheService.clear_pattern("centres:")
        return test

    @staticmethod
    async def get_test_by_id(db: AsyncSession, test_id: int) -> DiagnosticTest:
        """Fetch test by ID or raise HTTP 404."""
        query = select(DiagnosticTest).where(DiagnosticTest.id == test_id)
        result = await db.execute(query)
        test = result.scalar_one_or_none()
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Diagnostic test with ID {test_id} not found.",
            )
        return test
