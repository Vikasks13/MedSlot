from datetime import timedelta
import pytest
from httpx import AsyncClient

from app.utils.security import create_access_token


@pytest.mark.asyncio
async def test_signup_success(client: AsyncClient):
    """Test successful user registration."""
    payload = {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "password": "securepassword123",
    }
    response = await client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Jane Doe"
    assert data["email"] == "jane.doe@example.com"
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    """Test registering with an existing email returns 409 Conflict."""
    payload = {
        "name": "First User",
        "email": "duplicate@example.com",
        "password": "password123",
    }
    res1 = await client.post("/api/v1/auth/signup", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/signup", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_signup_validation_errors(client: AsyncClient):
    """Test validation errors for invalid email and short password."""
    # Invalid email
    res1 = await client.post(
        "/api/v1/auth/signup",
        json={"name": "Bad Email", "email": "not-an-email", "password": "password123"},
    )
    assert res1.status_code == 422

    # Short password (< 6 chars)
    res2 = await client.post(
        "/api/v1/auth/signup",
        json={"name": "Short Pass", "email": "valid@example.com", "password": "123"},
    )
    assert res2.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Test successful login returns valid JWT token."""
    # Register user first
    signup_payload = {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "password": "secretpassword",
    }
    await client.post("/api/v1/auth/signup", json=signup_payload)

    # Login
    login_payload = {
        "email": "bob@example.com",
        "password": "secretpassword",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test invalid password and non-existent email return 401."""
    # Register user
    await client.post(
        "/api/v1/auth/signup",
        json={"name": "User", "email": "user@example.com", "password": "correctpassword"},
    )

    # Wrong password
    res1 = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrongpassword"},
    )
    assert res1.status_code == 401
    assert "incorrect" in res1.json()["detail"].lower()

    # Non-existent email
    res2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "password"},
    )
    assert res2.status_code == 401


@pytest.mark.asyncio
async def test_login_oauth2_form(client: AsyncClient):
    """Test OAuth2 form endpoint for Swagger UI login."""
    await client.post(
        "/api/v1/auth/signup",
        json={"name": "OAuth User", "email": "oauth@example.com", "password": "password123"},
    )

    form_data = {
        "username": "oauth@example.com",
        "password": "password123",
    }
    response = await client.post(
        "/api/v1/auth/login/token",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_get_current_user_profile(client: AsyncClient):
    """Test retrieving authenticated user profile via /auth/me."""
    signup_res = await client.post(
        "/api/v1/auth/signup",
        json={"name": "Profile User", "email": "profile@example.com", "password": "password123"},
    )
    user_id = signup_res.json()["id"]

    # Login to get token
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "profile@example.com", "password": "password123"},
    )
    token = login_res.json()["access_token"]

    # Access /auth/me with valid Bearer token
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["id"] == user_id
    assert me_data["email"] == "profile@example.com"
    assert me_data["name"] == "Profile User"


@pytest.mark.asyncio
async def test_auth_unauthorized_scenarios(client: AsyncClient):
    """Test access denied on missing, invalid, and expired tokens."""
    # 1. Missing Authorization header
    res1 = await client.get("/api/v1/auth/me")
    assert res1.status_code == 401

    # 2. Invalid/tampered token
    res2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.string"},
    )
    assert res2.status_code == 401

    # 3. Expired token
    expired_token = create_access_token(
        subject=999,
        expires_delta=timedelta(minutes=-10),  # expired 10 minutes ago
    )
    res3 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res3.status_code == 401
