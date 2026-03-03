"""
Tests for the Authentication API endpoints.
"""
import pytest


@pytest.mark.asyncio
async def test_login_success(auth_client):
    """A valid login should return an access token."""
    # auth_client fixture already performed login; verify /me works
    resp = await auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testadmin"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """Wrong credentials should return 401."""
    # First complete setup so the user exists
    await client.post(
        "/api/setup/complete",
        json={
            "mode": "development",
            "database": {"type": "sqlite"},
            "admin": {
                "username": "admin",
                "email": "admin@example.com",
                "password": "SecurePass1!",
            },
        },
    )
    resp = await client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """Login for a non-existent user should return 401."""
    resp = await client.post(
        "/api/auth/login",
        data={"username": "nobody", "password": "pass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    """Accessing /me without a token should return 401."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_roles(auth_client):
    """Listing roles should return a non-empty list."""
    resp = await auth_client.get("/api/auth/roles")
    assert resp.status_code == 200
    roles = resp.json()
    assert isinstance(roles, list)
    assert len(roles) > 0


@pytest.mark.asyncio
async def test_list_users(auth_client):
    """Listing users should include the admin."""
    resp = await auth_client.get("/api/auth/users")
    assert resp.status_code == 200
    users = resp.json()
    assert any(u["username"] == "testadmin" for u in users)
