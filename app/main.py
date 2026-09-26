from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import engine, Base, get_db
from app.routers.auth import router as auth_router
from app.routers.centres import router as centres_router
from app.routers.bookings import router as bookings_router
from app.routers.payments import router as payments_router
from app.utils.exceptions import (
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.utils.logging import StructuredLoggingMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown events."""
    # Create tables if using SQLite for fast local prototyping
    if settings.async_database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: dispose database connection pool
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="EVE Healthcare Diagnostic Test Bookings and Simulated Payments API Service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Structured request logging middleware
app.add_middleware(StructuredLoggingMiddleware)

# Standardized Exception Handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)


# Register API Routers
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(centres_router, prefix=settings.API_V1_PREFIX)
app.include_router(bookings_router, prefix=settings.API_V1_PREFIX)
app.include_router(payments_router, prefix=settings.API_V1_PREFIX)
# Spec compatibility for root-level `/payments` and `/payments/webhook`
app.include_router(payments_router, prefix="", include_in_schema=False)


@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    status_code=status.HTTP_200_OK,
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Service health check endpoint.
    Verifies that the API and database are responding.
    """
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "version": "0.1.0",
    }


@app.get("/", tags=["System"], include_in_schema=False)
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs": "/docs",
        "health": "/health",
    }
