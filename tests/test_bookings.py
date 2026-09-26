from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient


async def create_user_and_token(client: AsyncClient, email: str, name: str) -> str:
    """Helper to create a user and return access token."""
    await client.post(
        "/api/v1/auth/signup",
        json={"name": name, "email": email, "password": "password123"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    return login_res.json()["access_token"]


async def create_test_centre_and_test(client: AsyncClient, token: str):
    """Helper to create a centre and a test under it."""
    c_res = await client.post(
        "/api/v1/centres",
        json={"name": "Max Healthcare", "location": "Saket, New Delhi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre_id = c_res.json()["id"]

    t_res = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={
            "name": "Thyroid Profile (T3, T4, TSH)",
            "description": "Comprehensive thyroid function evaluation",
            "price": 550.00,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    test_id = t_res.json()["id"]
    return centre_id, test_id


@pytest.mark.asyncio
async def test_create_booking_unauthenticated(client: AsyncClient):
    """Booking without token must return 401."""
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    response = await client.post(
        "/api/v1/bookings",
        json={"centre_id": 1, "test_id": 1, "appointment_date_time": future_time},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_booking_success(client: AsyncClient):
    """Test successful booking in PENDING state with price snapshot."""
    token = await create_user_and_token(client, "patient1@example.com", "John Doe")
    centre_id, test_id = await create_test_centre_and_test(client, token)

    future_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    booking_payload = {
        "centre_id": centre_id,
        "test_id": test_id,
        "appointment_date_time": future_time,
        "notes": "Fasting required for 10 hours",
    }
    response = await client.post(
        "/api/v1/bookings",
        json=booking_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert float(data["amount"]) == 550.00
    assert data["centre_id"] == centre_id
    assert data["test_id"] == test_id
    assert data["notes"] == "Fasting required for 10 hours"
    assert data["patient_name"] == "John Doe"
    assert data["centre_name"] == "Max Healthcare"
    assert data["test_name"] == "Thyroid Profile (T3, T4, TSH)"
    assert len(data["id"]) > 20  # Valid UUID


@pytest.mark.asyncio
async def test_create_booking_past_date(client: AsyncClient):
    """Booking with past appointment date must be rejected with 422."""
    token = await create_user_and_token(client, "patient_past@example.com", "Past Patient")
    centre_id, test_id = await create_test_centre_and_test(client, token)

    past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": past_time},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert "future" in str(response.json())


@pytest.mark.asyncio
async def test_create_booking_test_not_in_centre(client: AsyncClient):
    """Booking a test with a mismatched centre ID must return 400."""
    token = await create_user_and_token(client, "patient_mismatch@example.com", "Mismatch Patient")
    centre1_id, test1_id = await create_test_centre_and_test(client, token)

    # Create another centre
    c2_res = await client.post(
        "/api/v1/centres",
        json={"name": "Fortis Hospital", "location": "Gurgaon"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre2_id = c2_res.json()["id"]

    # Try booking test1 at centre2
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    response = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre2_id, "test_id": test1_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "not offered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_user_bookings_and_isolation(client: AsyncClient):
    """Users must only see their own bookings."""
    token_a = await create_user_and_token(client, "user_a@example.com", "User A")
    token_b = await create_user_and_token(client, "user_b@example.com", "User B")
    centre_id, test_id = await create_test_centre_and_test(client, token_a)

    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    # User A creates 2 bookings
    await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # User B creates 1 booking
    await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # User A views their bookings -> should see exactly 2
    res_a = await client.get("/api/v1/bookings", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    assert res_a.json()["total"] == 2
    assert len(res_a.json()["items"]) == 2

    # User B views their bookings -> should see exactly 1
    res_b = await client.get("/api/v1/bookings", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    assert res_b.json()["total"] == 1
    assert len(res_b.json()["items"]) == 1


@pytest.mark.asyncio
async def test_booking_ownership_access_control(client: AsyncClient):
    """User B cannot view or cancel User A's booking (403 Forbidden)."""
    token_a = await create_user_and_token(client, "victim@example.com", "Victim User")
    token_b = await create_user_and_token(client, "attacker@example.com", "Attacker User")
    centre_id, test_id = await create_test_centre_and_test(client, token_a)

    # User A creates booking
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    create_res = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    booking_id = create_res.json()["id"]

    # User B tries to view booking -> 403 Forbidden
    res_view = await client.get(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_view.status_code == 403

    # User B tries to cancel booking -> 403 Forbidden
    res_cancel = await client.patch(
        f"/api/v1/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_cancel.status_code == 403


@pytest.mark.asyncio
async def test_cancel_booking_state_machine(client: AsyncClient):
    """Test cancellation lifecycle and prevention of double cancellation."""
    token = await create_user_and_token(client, "canceller@example.com", "Canceller")
    centre_id, test_id = await create_test_centre_and_test(client, token)

    future_time = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
    create_res = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token}"},
    )
    booking_id = create_res.json()["id"]

    # Cancel booking
    cancel_res = await client.patch(
        f"/api/v1/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Attempting to cancel again must return 400 Bad Request
    dup_cancel = await client.patch(
        f"/api/v1/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dup_cancel.status_code == 400
    assert "already cancelled" in dup_cancel.json()["detail"].lower()
