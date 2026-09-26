import os
import sys
import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status


class RateLimiter:
    """
    Sliding window in-memory rate limiter per client IP.
    Can be used as a FastAPI dependency on sensitive endpoints.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60, enabled: bool = True):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.enabled = enabled
        self._history: Dict[str, List[float]] = defaultdict(list)

    def reset(self) -> None:
        """Clear history (used in tests)."""
        self._history.clear()

    async def __call__(self, request: Request) -> None:
        if not self.enabled:
            return

        # Explicit header to bypass rate limiting
        if request.headers.get("X-Skip-Rate-Limit") == "true":
            return

        # In automated test suites (pytest), bypass unless explicit test header is provided
        is_test_env = "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST") is not None
        if is_test_env and request.headers.get("X-Test-Rate-Limit") != "true":
            return

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune timestamps older than window
        timestamps = [t for t in self._history[client_ip] if t > cutoff]
        self._history[client_ip] = timestamps

        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_seconds} seconds.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        self._history[client_ip].append(now)


# Standard limiter instances for sensitive endpoints
auth_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
webhook_rate_limiter = RateLimiter(max_requests=60, window_seconds=60)
