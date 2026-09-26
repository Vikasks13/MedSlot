import pytest
from httpx import AsyncClient


async def get_auth_token(client: AsyncClient) -> str:
    """Helper to register and login a test user, returning the JWT token."""
    email = "centre_admin@example.com"
    pwd = "password123"
    await client.post(
        "/api/v1/auth/signup",
        json={"name": "Centre Admin", "email": email, "password": pwd},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
    )
    return login_res.json()["access_token"]


@pytest.mark.asyncio
async def test_create_centre_unauthenticated(client: AsyncClient):
    """Creating a centre without an auth token must return 401."""
    payload = {"name": "Metro Diagnostics", "location": "Connaught Place, Delhi"}
    response = await client.post("/api/v1/centres", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_centre_authenticated(client: AsyncClient):
    """Creating a centre with valid token returns 201 and created details."""
    token = await get_auth_token(client)
    payload = {
        "name": "Apollo Diagnostics",
        "location": "Koramangala, Bangalore",
        "contact_number": "+91-9876543210",
    }
    response = await client.post(
        "/api/v1/centres",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Apollo Diagnostics"
    assert data["location"] == "Koramangala, Bangalore"
    assert data["contact_number"] == "+91-9876543210"
    assert data["tests"] == []
    assert "id" in data


@pytest.mark.asyncio
async def test_get_centre_by_id(client: AsyncClient):
    """Test retrieving centre by ID and 404 on missing centre."""
    token = await get_auth_token(client)
    create_res = await client.post(
        "/api/v1/centres",
        json={"name": "Medall Healthcare", "location": "Adyar, Chennai"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre_id = create_res.json()["id"]

    # Success
    res = await client.get(f"/api/v1/centres/{centre_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Medall Healthcare"

    # Not found
    res_404 = await client.get("/api/v1/centres/99999")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_centres_and_pagination(client: AsyncClient):
    """Test pagination for diagnostic centres."""
    token = await get_auth_token(client)
    for i in range(5):
        await client.post(
            "/api/v1/centres",
            json={"name": f"Centre {i}", "location": f"City {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Page 1 with size 2
    res_p1 = await client.get("/api/v1/centres?page=1&size=2")
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert len(d1["items"]) == 2
    assert d1["total"] == 5
    assert d1["total_pages"] == 3
    assert d1["page"] == 1

    # Page 3 with size 2 (should have 1 item)
    res_p3 = await client.get("/api/v1/centres?page=3&size=2")
    assert res_p3.status_code == 200
    d3 = res_p3.json()
    assert len(d3["items"]) == 1


@pytest.mark.asyncio
async def test_filter_centres_by_location_and_search(client: AsyncClient):
    """Test filtering centres by location and name substring."""
    token = await get_auth_token(client)
    await client.post(
        "/api/v1/centres",
        json={"name": "Max Lab", "location": "South Delhi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/v1/centres",
        json={"name": "Fortis Diagnostics", "location": "Mumbai West"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Filter by location
    res_loc = await client.get("/api/v1/centres?location=delhi")
    assert res_loc.status_code == 200
    assert len(res_loc.json()["items"]) == 1
    assert res_loc.json()["items"][0]["name"] == "Max Lab"

    # Filter by search
    res_search = await client.get("/api/v1/centres?search=Fortis")
    assert res_search.status_code == 200
    assert len(res_search.json()["items"]) == 1
    assert res_search.json()["items"][0]["location"] == "Mumbai West"


@pytest.mark.asyncio
async def test_add_test_to_centre(client: AsyncClient):
    """Test adding diagnostic test to centre with price validation."""
    token = await get_auth_token(client)
    c_res = await client.post(
        "/api/v1/centres",
        json={"name": "Thyrocare Centre", "location": "Navi Mumbai"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre_id = c_res.json()["id"]

    # Add test
    test_payload = {
        "name": "Complete Blood Count (CBC)",
        "description": "Measures white blood cells, red blood cells, and platelets",
        "price": 350.00,
    }
    t_res = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json=test_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert t_res.status_code == 201
    test_data = t_res.json()
    assert test_data["name"] == "Complete Blood Count (CBC)"
    assert float(test_data["price"]) == 350.00
    assert test_data["centre_id"] == centre_id

    # Retrieve centre and verify nested test is returned
    centre_detail = await client.get(f"/api/v1/centres/{centre_id}")
    assert centre_detail.status_code == 200
    assert len(centre_detail.json()["tests"]) == 1
    assert centre_detail.json()["tests"][0]["name"] == "Complete Blood Count (CBC)"

    # List tests endpoint
    tests_list = await client.get(f"/api/v1/centres/{centre_id}/tests")
    assert tests_list.status_code == 200
    assert len(tests_list.json()) == 1


@pytest.mark.asyncio
async def test_add_test_edge_cases(client: AsyncClient):
    """Test duplicate test name in same centre and non-existent centre."""
    token = await get_auth_token(client)
    c_res = await client.post(
        "/api/v1/centres",
        json={"name": "SRL Diagnostics", "location": "Gurgaon"},
        headers={"Authorization": f"Bearer {token}"},
    )
    centre_id = c_res.json()["id"]

    test_payload = {"name": "Lipid Profile", "price": 800.00}
    res1 = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json=test_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 201

    # Duplicate test name in same centre -> 409 Conflict
    res_dup = await client.post(
        f"/api/v1/centres/{centre_id}/tests",
        json=test_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_dup.status_code == 409
    assert "already exists" in res_dup.json()["detail"].lower()

    # Add test to non-existent centre -> 404 Not Found
    res_404 = await client.post(
        "/api/v1/centres/99999/tests",
        json={"name": "Random Test", "price": 100.00},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_404.status_code == 404
