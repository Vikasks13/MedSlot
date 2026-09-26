from app.routers.auth import router as auth_router
from app.routers.centres import router as centres_router
from app.routers.bookings import router as bookings_router

__all__ = ["auth_router", "centres_router", "bookings_router"]
