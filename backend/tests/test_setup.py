"""
Tests for the Setup Wizard API endpoints.

These all use `anon_client`: the wizard runs before any account exists, so it
must stay reachable without credentials.
"""
import pytest


@pytest.mark.asyncio
async def test_setup_status_not_completed(anon_client):
    """Setup status should report not-completed on a fresh database."""
    resp = await anon_client.get("/api/setup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["setup_completed"] is False
    assert data["mode"] is None


@pytest.mark.asyncio
async def test_setup_demo_mode(anon_client):
    """Demo mode should activate and seed sample data."""
    resp = await anon_client.post("/api/setup/demo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "demo"

    # Setup should now be marked completed
    status = await anon_client.get("/api/setup/status")
    assert status.json()["setup_completed"] is True
    assert status.json()["mode"] == "demo"


@pytest.mark.asyncio
async def test_setup_demo_cannot_run_twice(anon_client):
    """Running demo setup twice should return 400."""
    await anon_client.post("/api/setup/demo")
    resp = await anon_client.post("/api/setup/demo")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_setup_complete_development(anon_client):
    """Development mode setup should succeed and create an admin account."""
    resp = await anon_client.post(
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
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "development"
    assert data["db_type"] == "sqlite"


@pytest.mark.asyncio
async def test_setup_complete_invalid_mode(anon_client):
    """An invalid mode should return 400."""
    resp = await anon_client.post(
        "/api/setup/complete",
        json={
            "mode": "invalid",
            "database": {"type": "sqlite"},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_setup_complete_production_requires_admin(anon_client):
    """Production mode without admin config should return 400."""
    resp = await anon_client.post(
        "/api/setup/complete",
        json={"mode": "production", "database": {"type": "sqlite"}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_setup_test_db_sqlite(anon_client):
    """Testing an SQLite connection should always succeed."""
    resp = await anon_client.post(
        "/api/setup/test-db", json={"type": "sqlite"}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
