import pytest
from httpx import AsyncClient

from app.utils.rate_limit import auth_rate_limiter


@pytest.mark.asyncio
async def test_standardized_404_error_format(client: AsyncClient):
    """Verify non-existent routes return standardized JSON error format."""
    response = await client.get("/api/v1/non-existent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert data["status_code"] == 404
    assert data["error_type"] == "HTTPException"
    assert "detail" in data
    assert data["path"] == "/api/v1/non-existent-endpoint"


@pytest.mark.asyncio
async def test_standardized_422_validation_error_format(client: AsyncClient):
    """Verify invalid payloads return structured validation error messages."""
    response = await client.post(
        "/api/v1/auth/signup",
        json={"name": "A", "email": "invalid-email", "password": "123"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["status_code"] == 422
    assert data["error_type"] == "ValidationError"
    assert isinstance(data["detail"], list)
    assert len(data["detail"]) >= 1
    # Check each error has field, message, and type
    assert "field" in data["detail"][0]
    assert "message" in data["detail"][0]


@pytest.mark.asyncio
async def test_process_time_header_present(client: AsyncClient):
    """Verify X-Process-Time-Ms header is injected by logging middleware."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "x-process-time-ms" in response.headers
    assert float(response.headers["x-process-time-ms"]) >= 0


@pytest.mark.asyncio
async def test_rate_limiter_exceeded_triggers_429(client: AsyncClient):
    """Verify exceeding rate limit returns 429 with Retry-After header."""
    auth_rate_limiter.reset()

    # Trigger requests up to limit
    for _ in range(auth_rate_limiter.max_requests):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
            headers={"X-Test-Rate-Limit": "true"},
        )

    # Next request must be rate-limited (429)
    rate_limited_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
        headers={"X-Test-Rate-Limit": "true"},
    )
    assert rate_limited_res.status_code == 429
    assert "rate limit exceeded" in rate_limited_res.json()["detail"].lower()
    assert "retry-after" in rate_limited_res.headers

    # Reset so other tests are not impacted
    auth_rate_limiter.reset()


@pytest.mark.asyncio
async def test_webhook_invalid_secret_header(client: AsyncClient):
    """Verify webhook rejects mismatched X-Webhook-Secret header."""
    auth_rate_limiter.reset()
    payload = {
        "event_id": "evt_secret_test_001",
        "booking_id": "random-uuid",
        "amount": 500.00,
        "status": "SUCCESS",
    }
    response = await client.post(
        "/api/v1/payments/webhook",
        json=payload,
        headers={"X-Webhook-Secret": "invalid_wrong_secret_key"},
    )
    assert response.status_code == 401
    assert "secret" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_diagnostic_test_price_boundary(client: AsyncClient):
    """Verify negative or zero prices are rejected with 422."""
    auth_rate_limiter.reset()
    # 1. Signup and login
    email = "boundary_admin@example.com"
    await client.post(
        "/api/v1/auth/signup",
        json={"name": "Boundary Admin", "email": email, "password": "password123"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_res.json()["access_token"]

    # 2. Create centre
    c_res = await client.post(
        "/api/v1/centres",
        json={"name": "Boundary Diagnostics", "location": "Sector 62, Noida"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre_id = c_res.json()["id"]

    # 3. Add test with 0.00 price -> rejected
    zero_price_res = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"name": "Free Test", "price": 0.00},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert zero_price_res.status_code == 422

    # 4. Add test with negative price -> rejected
    neg_price_res = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"name": "Negative Price Test", "price": -150.00},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert neg_price_res.status_code == 422
