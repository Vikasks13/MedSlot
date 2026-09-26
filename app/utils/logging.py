import logging
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Configure standard logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("medslot.access")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that records structured access logs for each request,
    including HTTP method, path, status code, client IP, and execution duration.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "%s %s -> %s %s (%.2f ms) - IP: %s",
                request.method,
                request.url.path,
                response.status_code,
                response.headers.get("content-type", ""),
                duration_ms,
                client_host,
            )
            response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "%s %s -> FAILED with %s (%.2f ms) - IP: %s",
                request.method,
                request.url.path,
                type(exc).__name__,
                duration_ms,
                client_host,
                exc_info=True,
            )
            raise
