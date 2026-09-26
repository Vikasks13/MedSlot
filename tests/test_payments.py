from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Tuple
import pytest
from httpx import AsyncClient


async def setup_booking(client: AsyncClient, email: str, name: str) -> Tuple[str, str, Decimal]:
    """Helper to create user, centre, test, and booking, returning (token, booking_id, amount)."""
    # 1. Register & login
    await client.post(
        "/api/v1/auth/signup",
        json={"name": name, "email": email, "password": "password123"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_res.json()["access_token"]

    # 2. Create centre & test
    c_res = await client.post(
        "/api/v1/centres",
        json={"name": "Care Diagnostic Clinic", "location": "Whitefield, Bangalore"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre_id = c_res.json()["id"]

    t_res = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json={"name": "HbA1c Glycated Hemoglobin", "price": 600.00},
        headers={"Authorization": f"Bearer {token}"},
    )
    test_id = t_res.json()["id"]

    # 3. Create booking
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    b_res = await client.post(
        "/api/v1/bookings",
        json={"centre_id": centre_id, "test_id": test_id, "appointment_date_time": future_time},
        headers={"Authorization": f"Bearer {token}"},
    )
    booking_id = b_res.json()["id"]
    return token, booking_id, Decimal("600.00")


from typing import Tuple


@pytest.mark.asyncio
async def test_simulated_payment_success(client: AsyncClient):
    """Test simulated payment success transitions booking to CONFIRMED."""
    token, booking_id, amount = await setup_booking(client, "pay_success@example.com", "Pay Success")

    pay_payload = {
        "booking_id": booking_id,
        "payment_method": "UPI",
        "simulate_status": "SUCCESS",
    }
    response = await client.post(
        "/api/v1/payments",
        json=pay_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["booking_status"] == "CONFIRMED"
    assert float(data["amount"]) == float(amount)
    assert "idempotency_key" in data

    # Verify booking detail endpoint also shows CONFIRMED
    booking_check = await client.get(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert booking_check.status_code == 200
    assert booking_check.json()["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_simulated_payment_failure(client: AsyncClient):
    """Test simulated payment failure transitions booking to FAILED."""
    token, booking_id, amount = await setup_booking(client, "pay_fail@example.com", "Pay Fail")

    pay_payload = {
        "booking_id": booking_id,
        "payment_method": "CREDIT_CARD",
        "simulate_status": "FAILED",
    }
    response = await client.post(
        "/api/v1/payments",
        json=pay_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "FAILED"
    assert data["booking_status"] == "FAILED"
    assert data["failure_reason"] is not None

    # Check booking status is FAILED
    booking_check = await client.get(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert booking_check.json()["status"] == "FAILED"


@pytest.mark.asyncio
async def test_simulated_payment_forbidden_for_other_users(client: AsyncClient):
    """User B cannot pay for User A's booking."""
    token_a, booking_id, _ = await setup_booking(client, "user_a_pay@example.com", "User A")

    # Create User B
    await client.post(
        "/api/v1/auth/signup",
        json={"name": "User B", "email": "user_b_pay@example.com", "password": "password123"},
    )
    login_b = await client.post(
        "/api/v1/auth/login",
        json={"email": "user_b_pay@example.com", "password": "password123"},
    )
    token_b = login_b.json()["access_token"]

    response = await client.post(
        "/api/v1/payments",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_simulated_payment_already_confirmed_or_cancelled(client: AsyncClient):
    """Cannot pay for already CONFIRMED or CANCELLED bookings."""
    token, booking_id, _ = await setup_booking(client, "state_check@example.com", "State Check")

    # Pay once -> CONFIRMED
    await client.post(
        "/api/v1/payments",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Pay again -> 400 Bad Request
    res_again = await client.post(
        "/api/v1/payments",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_again.status_code == 400
    assert "already" in res_again.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_idempotency_sent_multiple_times(client: AsyncClient):
    """
    CRITICAL REQUIREMENT:
    If the same webhook/event is received multiple times, it must not create
    duplicate payments, duplicate bookings, or otherwise corrupt the booking state.
    """
    token, booking_id, amount = await setup_booking(client, "webhook_user@example.com", "Webhook User")

    webhook_payload = {
        "event_id": "evt_test_unique_998877",
        "event_type": "payment.succeeded",
        "booking_id": booking_id,
        "amount": float(amount),
        "status": "SUCCESS",
        "payment_method": "RAZORPAY_SIMULATED",
    }

    # Delivery 1: Should be processed successfully
    res1 = await client.post("/api/v1/payments/webhook", json=webhook_payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "processed"
    assert data1["booking_status"] == "CONFIRMED"
    first_payment_id = data1["payment_id"]

    # Delivery 2: Exact same webhook event sent again
    res2 = await client.post("/api/v1/payments/webhook", json=webhook_payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "already_processed"
    assert data2["payment_id"] == first_payment_id
    assert "already processed" in data2["message"].lower()

    # Delivery 3: Exact same webhook event sent a third time
    res3 = await client.post("/api/v1/payments/webhook", json=webhook_payload)
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["status"] == "already_processed"
    assert data3["payment_id"] == first_payment_id

    # Verify final booking state is cleanly CONFIRMED
    booking_res = await client.get(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert booking_res.json()["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_webhook_failed_payment(client: AsyncClient):
    """Webhook event with status FAILED transitions PENDING booking to FAILED."""
    token, booking_id, amount = await setup_booking(client, "webhook_fail@example.com", "Webhook Fail")

    webhook_payload = {
        "event_id": "evt_test_fail_112233",
        "event_type": "payment.failed",
        "booking_id": booking_id,
        "amount": float(amount),
        "status": "FAILED",
        "failure_reason": "Insufficient balance in customer account",
    }

    res = await client.post("/api/v1/payments/webhook", json=webhook_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processed"
    assert data["booking_status"] == "FAILED"

    # Verify booking is FAILED
    booking_res = await client.get(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert booking_res.json()["status"] == "FAILED"


@pytest.mark.asyncio
async def test_webhook_nonexistent_booking(client: AsyncClient):
    """Webhook for unknown booking must return 404."""
    webhook_payload = {
        "event_id": "evt_unknown_booking_404",
        "booking_id": "non-existent-booking-uuid-00000",
        "amount": 500.00,
        "status": "SUCCESS",
    }
    response = await client.post("/api/v1/payments/webhook", json=webhook_payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_spec_exact_paths_compatibility(client: AsyncClient):
    """Verify exact endpoints POST /payments/ and POST /payments/webhook/ work per assignment specification."""
    token, booking_id, amount = await setup_booking(client, "spec_paths@example.com", "Spec User")

    # POST /payments (or /payments/)
    sim_res = await client.post(
        "/payments",
        json={"booking_id": booking_id, "simulate_status": "SUCCESS"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sim_res.status_code == 200
    assert sim_res.json()["status"] == "SUCCESS"

    # POST /payments/webhook
    wh_payload = {
        "event_id": "evt_spec_exact_path_777",
        "booking_id": booking_id,
        "amount": 600.00,
        "status": "SUCCESS",
    }
    wh_res = await client.post("/payments/webhook", json=wh_payload)
    assert wh_res.status_code == 200
    assert wh_res.json()["status"] == "already_processed" or wh_res.json()["status"] == "processed"
