"""
Tests for the Heartbeat / Fail-Safe Monitors API endpoints.
"""
import pytest


@pytest.mark.asyncio
async def test_list_monitors_empty(client):
    """Monitor list should be empty on a fresh database."""
    resp = await client.get("/api/monitors/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_monitor(client):
    """Creating a monitor should succeed and assign a unique ping_key."""
    resp = await client.post(
        "/api/monitors/",
        json={
            "name": "Daily Backup",
            "description": "Heartbeat for backup job",
            "expected_interval_seconds": 86400,
            "grace_period_seconds": 300,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Daily Backup"
    assert data["status"] == "new"
    assert len(data["ping_key"]) > 0


@pytest.mark.asyncio
async def test_create_monitor_duplicate_name(client):
    """Duplicate monitor names should return 400."""
    payload = {"name": "Dup Monitor", "expected_interval_seconds": 300, "grace_period_seconds": 60}
    await client.post("/api/monitors/", json=payload)
    resp = await client.post("/api/monitors/", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_monitor(client):
    """Getting a monitor by ID should return its data."""
    create = await client.post(
        "/api/monitors/",
        json={"name": "Test Monitor", "expected_interval_seconds": 600},
    )
    monitor_id = create.json()["id"]
    resp = await client.get(f"/api/monitors/{monitor_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Monitor"


@pytest.mark.asyncio
async def test_get_monitor_not_found(client):
    """Getting a non-existent monitor should return 404."""
    resp = await client.get("/api/monitors/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_monitor(client):
    """Updating a monitor should persist the change."""
    create = await client.post(
        "/api/monitors/",
        json={"name": "Old Monitor Name", "expected_interval_seconds": 300},
    )
    monitor_id = create.json()["id"]
    resp = await client.put(
        f"/api/monitors/{monitor_id}",
        json={"name": "New Monitor Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Monitor Name"


@pytest.mark.asyncio
async def test_delete_monitor(client):
    """Deleting a monitor should return 204 and remove it."""
    create = await client.post(
        "/api/monitors/",
        json={"name": "To Delete Monitor", "expected_interval_seconds": 300},
    )
    monitor_id = create.json()["id"]
    resp = await client.delete(f"/api/monitors/{monitor_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/monitors/{monitor_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ping_monitor(client):
    """Pinging a monitor using its key should return a success message."""
    create = await client.post(
        "/api/monitors/",
        json={"name": "Pingable Monitor", "expected_interval_seconds": 300},
    )
    data = create.json()
    ping_key = data["ping_key"]

    resp = await client.post(f"/api/monitors/ping/{ping_key}")
    assert resp.status_code == 200
    assert "message" in resp.json()


@pytest.mark.asyncio
async def test_ping_invalid_key(client):
    """Pinging with an unknown key should return 404."""
    resp = await client.post("/api/monitors/ping/invalid-key-xyz")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_monitor_pings(client):
    """Listing pings for a monitor should return recent ping history."""
    create = await client.post(
        "/api/monitors/",
        json={"name": "History Monitor", "expected_interval_seconds": 300},
    )
    data = create.json()
    monitor_id = data["id"]
    ping_key = data["ping_key"]

    await client.post(f"/api/monitors/ping/{ping_key}")
    resp = await client.get(f"/api/monitors/{monitor_id}/pings")
    assert resp.status_code == 200
    pings = resp.json()
    assert len(pings) >= 1
