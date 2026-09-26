import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import get_settings
from app.models.booking import Booking, BookingStatus
from app.models.centre import DiagnosticCentre
from app.models.payment import Payment, PaymentStatus
from app.models.test import DiagnosticTest
from app.models.user import User
from app.services.booking_service import BookingService
from app.services.centre_service import CentreService
from app.services.payment_service import PaymentService
from app.utils.cache import CacheService, _memory_cache
from app.utils.exceptions import global_exception_handler
from app.utils.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

settings = get_settings()


async def get_token_for(client: AsyncClient, name: str, email: str) -> tuple[str, int]:
    await client.post(
        "/api/v1/auth/signup",
        json={"name": name, "email": email, "password": "password123"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_res.json()["access_token"]
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = me_res.json()["id"]
    return token, user_id


@pytest.mark.asyncio
async def test_inactive_user_login_and_access(client: AsyncClient, db_session: AsyncSession):
    """Verify that deactivated users cannot login and cannot access protected endpoints."""
    email = "inactive_user@example.com"
    token, user_id = await get_token_for(client, "Inactive User", email)

    # Deactivate user in DB
    result = await db_session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    # 1. Login attempt must fail with 403
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login_res.status_code == 403
    assert "inactive" in login_res.json()["detail"].lower()

    # 2. Access with previous token must fail with 403
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 403
    assert "inactive" in me_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_jwt_and_security_utilities(client: AsyncClient):
    """Verify security utilities, extra claims, and invalid token branches."""
    # 1. Extra claims in token
    extra_token = create_access_token(subject=123, extra_claims={"custom_role": "manager"})
    claims = decode_access_token(extra_token)
    assert claims["custom_role"] == "manager"

    # 2. Token without sub
    no_sub_token = jwt.encode({"iat": 12345}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {no_sub_token}"})
    assert res.status_code == 401

    # 3. Token with non-integer sub
    invalid_sub_token = jwt.encode({"sub": "not-an-int"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {invalid_sub_token}"})
    assert res.status_code == 401

    # 4. Token with non-existent user ID
    ghost_token = create_access_token(subject=999999)
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ghost_token}"})
    assert res.status_code == 401

    # 5. verify_password error handling
    assert verify_password("pass", "invalid-hash-string") is False


@pytest.mark.asyncio
async def test_booking_service_error_branches(client: AsyncClient):
    """Verify booking 404s, cancelling FAILED bookings, and 0 bookings list."""
    token, user_id = await get_token_for(client, "Booking Tester", "booking_tester@example.com")
    auth_header = {"Authorization": f"Bearer {token}"}

    # 1. Non-existent centre
    res = await client.post(
        "/api/v1/bookings",
        json={
            "centre_id": 99999,
            "test_id": 1,
            "appointment_date_time": "2026-12-01T10:00:00Z",
        },
        headers=auth_header,
    )
    assert res.status_code == 404
    assert "centre with id 99999 not found" in res.json()["detail"].lower()

    # 2. Create valid centre
    c_res = await client.post(
        "/api/v1/centres",
        json={"name": "City Clinic", "location": "Central Hub"},
        headers=auth_header,
    )
    centre_id = c_res.json()["id"]

    # 3. Non-existent test under valid centre
    res = await client.post(
        "/api/v1/bookings",
        json={
            "centre_id": centre_id,
            "test_id": 99999,
            "appointment_date_time": "2026-12-01T10:00:00Z",
        },
        headers=auth_header,
    )
    assert res.status_code == 404
    assert "test with id 99999 not found" in res.json()["detail"].lower()

    # 4. Non-existent booking lookup
    res = await client.get("/api/v1/bookings/00000000-0000-0000-0000-000000000000", headers=auth_header)
    assert res.status_code == 404

    # 5. Create valid test and booking, then fail payment, then attempt cancellation
    t_res = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"name": "Lipid Profile", "price": 750.00},
        headers=auth_header,
    )
    test_id = t_res.json()["id"]

    b_res = await client.post(
        "/api/v1/bookings",
        json={
            "centre_id": centre_id,
            "test_id": test_id,
            "appointment_date_time": "2026-12-01T10:00:00Z",
        },
        headers=auth_header,
    )
    booking_id = b_res.json()["id"]

    # Fail payment
    await client.post(
        "/api/v1/payments",
        json={"booking_id": booking_id, "simulate_status": "FAILED"},
        headers=auth_header,
    )

    # Cancel a FAILED booking must return 400
    cancel_res = await client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=auth_header)
    assert cancel_res.status_code == 400
    assert "already failed" in cancel_res.json()["detail"].lower()

    # 6. User with 0 bookings
    new_token, _ = await get_token_for(client, "Empty User", "empty_user@example.com")
    res = await client.get("/api/v1/bookings", headers={"Authorization": f"Bearer {new_token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert res.json()["items"] == []


@pytest.mark.asyncio
async def test_centre_and_test_lookups_404(client: AsyncClient):
    """Verify 404s for missing centre and test IDs."""
    res1 = await client.get("/api/v1/centres/99999")
    assert res1.status_code == 404

    res2 = await client.get("/api/v1/centres/99999/tests")
    assert res2.status_code == 404

    res3 = await client.get("/api/v1/tests/99999")
    assert res3.status_code == 404


@pytest.mark.asyncio
async def test_payment_service_comprehensive_cases(client: AsyncClient):
    """Verify payment retrieval, ownership, cancelled booking payment, and default simulate status."""
    token, user_id = await get_token_for(client, "Pay User", "pay_user@example.com")
    auth_header = {"Authorization": f"Bearer {token}"}

    other_token, _ = await get_token_for(client, "Other Pay User", "other_pay_user@example.com")
    other_header = {"Authorization": f"Bearer {other_token}"}

    # 1. Non-existent booking payment
    res = await client.post(
        "/api/v1/payments",
        json={"booking_id": "00000000-0000-0000-0000-000000000000", "simulate_status": "SUCCESS"},
        headers=auth_header,
    )
    assert res.status_code == 404

    # 2. Setup centre, test, and booking
    c_res = await client.post("/api/v1/centres", json={"name": "Metro Lab", "location": "Metro"}, headers=auth_header)
    centre_id = c_res.json()["id"]
    t_res = await client.post(f"/api/v1/centres/{centre_id}/tests", json={"name": "Thyroid Test", "price": 500.00}, headers=auth_header)
    test_id = t_res.json()["id"]

    # 3. Pay for CANCELLED booking
    b_res = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": "2026-12-05T10:00:00Z"},
        headers=auth_header,
    )
    booking_id = b_res.json()["id"]
    await client.patch(f"/api/v1/bookings/{booking_id}/cancel", headers=auth_header)

    cancel_pay_res = await client.post(
        "/api/v1/payments",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers=auth_header,
    )
    assert cancel_pay_res.status_code == 400
    assert "cancelled" in cancel_pay_res.json()["detail"].lower()

    # 4. Default simulate_status branch (without simulate_status field)
    b2_res = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": "2026-12-06T10:00:00Z"},
        headers=auth_header,
    )
    b2_id = b2_res.json()["id"]
    default_pay_res = await client.post(
        "/api/v1/payments",
        json={"booking_id": b2_id},
        headers=auth_header,
    )
    assert default_pay_res.status_code == 200
    payment_id = default_pay_res.json()["id"]
    assert default_pay_res.json()["status"] in ["SUCCESS", "FAILED"]

    # 5. GET payment by ID (Owner success)
    get_pay_res = await client.get(f"/api/v1/payments/{payment_id}", headers=auth_header)
    assert get_pay_res.status_code == 200
    assert get_pay_res.json()["id"] == payment_id

    # 6. GET payment by ID (Other user forbidden)
    forbidden_pay_res = await client.get(f"/api/v1/payments/{payment_id}", headers=other_header)
    assert forbidden_pay_res.status_code == 403

    # 7. GET payment non-existent
    not_found_res = await client.get("/api/v1/payments/non-existent-uuid", headers=auth_header)
    assert not_found_res.status_code == 404


@pytest.mark.asyncio
async def test_cache_service_in_memory_and_mocked_redis():
    """Direct unit testing of CacheService in-memory & mocked Redis pathways."""
    # In-memory tests
    _memory_cache.clear()
    await CacheService.set("test:key1", {"msg": "hello"}, ttl=10)
    val = await CacheService.get("test:key1")
    assert val == {"msg": "hello"}

    # Expired key
    _memory_cache["test:expired"] = (json.dumps("old"), time.time() - 5)
    assert await CacheService.get("test:expired") is None

    # Clear pattern
    await CacheService.set("test:key2", 123)
    await CacheService.clear_pattern("test:")
    assert await CacheService.get("test:key1") is None
    assert await CacheService.get("test:key2") is None

    # Mock Redis client tests
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps({"redis": True})
    mock_redis.keys.return_value = ["prefix:1", "prefix:2"]

    CacheService._redis_client = mock_redis
    CacheService._redis_available = True

    try:
        # Redis GET
        res = await CacheService.get("some_key")
        assert res == {"redis": True}
        mock_redis.get.assert_called_with("some_key")

        # Redis SET
        await CacheService.set("some_key", {"a": 1}, ttl=30)
        mock_redis.set.assert_called_once()

        # Redis clear pattern
        await CacheService.clear_pattern("prefix:")
        mock_redis.delete.assert_called_with("prefix:1", "prefix:2")
    finally:
        CacheService._redis_client = None
        CacheService._redis_available = None


@pytest.mark.asyncio
async def test_global_exception_handler_direct():
    """Verify global exception handler catches errors and sanitizes output."""
    scope = {"type": "http", "method": "GET", "path": "/crash-test", "headers": []}
    mock_request = Request(scope)
    response = await global_exception_handler(mock_request, RuntimeError("Secret DB password failed"))
    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["status_code"] == 500
    assert body["error_type"] == "InternalServerError"
    assert "Secret DB password" not in body["detail"]
    assert "unexpected internal server error" in body["detail"].lower()


@pytest.mark.asyncio
async def test_models_repr_coverage():
    """Verify __repr__ methods on models for logging/debugging coverage."""
    user = User(id=1, email="test@example.com", name="Test")
    centre = DiagnosticCentre(id=1, name="Centre A", location="Loc A")
    diag_test = DiagnosticTest(id=1, name="Test 1", price=100.0)
    booking = Booking(id="test-uuid", user_id=1, centre_id=1, test_id=1, status=BookingStatus.PENDING)
    payment = Payment(id="pay-uuid", booking_id="test-uuid", amount=100.0, status=PaymentStatus.SUCCESS)

    assert "test@example.com" in repr(user)
    assert "Centre A" in repr(centre)
    assert "Test 1" in repr(diag_test)
    assert "test-uuid" in repr(booking)
    assert "pay-uuid" in repr(payment)


@pytest.mark.asyncio
async def test_filter_user_bookings_and_empty_centre_search(client: AsyncClient):
    """Verify booking status filter branch and empty centre search branch."""
    token, user_id = await get_token_for(client, "Filter User", "filter_user@example.com")
    auth_header = {"Authorization": f"Bearer {token}"}

    # 1. Centre search yielding 0 results (line 62 of centre_service)
    res = await client.get("/api/v1/centres?search=NonExistentClinicZXY999")
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert res.json()["items"] == []

    # 2. Setup centre and test
    c_res = await client.post("/api/v1/centres", json={"name": "Specialty Centre", "location": "Sector 18"}, headers=auth_header)
    centre_id = c_res.json()["id"]
    t_res = await client.post(f"/api/v1/centres/{centre_id}/tests", json={"name": "Serum Iron", "price": 300.00}, headers=auth_header)
    test_id = t_res.json()["id"]

    # 3. Get existing test directly by ID (line 161 of centre_service)
    get_t_res = await client.get(f"/api/v1/tests/{test_id}")
    assert get_t_res.status_code == 200
    assert get_t_res.json()["name"] == "Serum Iron"

    # 4. Create booking and query with status_filter (line 128 of booking_service)
    await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": "2026-11-20T10:00:00Z"},
        headers=auth_header,
    )
    filter_res = await client.get("/api/v1/bookings?status=PENDING", headers=auth_header)
    assert filter_res.status_code == 200
    assert filter_res.json()["total"] == 1


@pytest.mark.asyncio
async def test_webhook_concurrent_integrity_error_branch(db_session: AsyncSession):
    """Directly test concurrent IntegrityError race handling in webhook processor."""
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError
    from app.schemas.payment import PaymentWebhookPayload

    # Create dummy booking
    user = User(name="Concurrency User", email="concurrency@example.com", password_hash="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    centre = DiagnosticCentre(name="Race Centre", location="Race Loc")
    db_session.add(centre)
    await db_session.flush()

    test = DiagnosticTest(centre_id=centre.id, name="Race Test", price=100.0)
    db_session.add(test)
    await db_session.flush()

    booking = Booking(
        id="race-booking-uuid-001",
        user_id=user.id,
        centre_id=centre.id,
        test_id=test.id,
        appointment_date_time=datetime.now(timezone.utc) + timedelta(days=2),
        amount=100.0,
        status=BookingStatus.PENDING,
    )
    db_session.add(booking)
    await db_session.flush()

    payload = PaymentWebhookPayload(
        event_id="evt_race_001",
        booking_id=booking.id,
        amount=100.0,
        status=PaymentStatus.SUCCESS,
    )

    # Patch flush to simulate another worker inserting the exact same event_id concurrently
    original_flush = db_session.flush
    async def mock_flush():
        raise IntegrityError("duplicate key value violates unique constraint", params={}, orig=Exception("unique constraint"))

    with patch.object(db_session, "flush", side_effect=mock_flush):
        status_msg, message, payment_id, b_status = await PaymentService.process_webhook_event(db_session, payload)
        assert status_msg == "already_processed"
        assert "concurrently" in message


@pytest.mark.asyncio
async def test_health_check_degraded_branch():
    """Verify health check returns degraded status when DB is unreachable."""
    from app.main import health_check

    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute.side_effect = RuntimeError("Database connection timed out")

    res = await health_check(db=mock_db)
    assert res["status"] == "degraded"
    assert "unhealthy" in res["database"]

