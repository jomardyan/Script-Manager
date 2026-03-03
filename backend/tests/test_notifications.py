"""
Tests for the Notification Channels and Incidents API endpoints.
"""
import pytest


# ── Notification Channels ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_channels_empty(client):
    """Channels list should be empty on a fresh database."""
    resp = await client.get("/api/notifications/channels/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_channel(client):
    """Creating a valid channel should succeed."""
    resp = await client.post(
        "/api/notifications/channels/",
        json={"name": "My Slack", "type": "slack", "config": {"token": "xoxb-test"}, "enabled": True},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Slack"
    assert data["type"] == "slack"
    assert isinstance(data["id"], int)


@pytest.mark.asyncio
async def test_create_channel_invalid_type(client):
    """Creating a channel with an unknown type should return 400."""
    resp = await client.post(
        "/api/notifications/channels/",
        json={"name": "Bad Channel", "type": "telepathy", "config": {}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_channel_duplicate_name(client):
    """Duplicate channel names should return 400."""
    payload = {"name": "Duplicate", "type": "webhook", "config": {"url": "http://x.com"}}
    await client.post("/api/notifications/channels/", json=payload)
    resp = await client.post("/api/notifications/channels/", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_channel(client):
    """Getting a channel by ID should return its data."""
    create = await client.post(
        "/api/notifications/channels/",
        json={"name": "Discord Alert", "type": "discord", "config": {}},
    )
    channel_id = create.json()["id"]
    resp = await client.get(f"/api/notifications/channels/{channel_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Discord Alert"


@pytest.mark.asyncio
async def test_get_channel_not_found(client):
    """Getting a non-existent channel should return 404."""
    resp = await client.get("/api/notifications/channels/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_channel(client):
    """Updating a channel should persist changes."""
    create = await client.post(
        "/api/notifications/channels/",
        json={"name": "Old Name", "type": "email", "config": {}},
    )
    channel_id = create.json()["id"]
    resp = await client.put(
        f"/api/notifications/channels/{channel_id}",
        json={"name": "New Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_channel(client):
    """Deleting a channel should return 204 and remove it."""
    create = await client.post(
        "/api/notifications/channels/",
        json={"name": "To Delete", "type": "webhook", "config": {}},
    )
    channel_id = create.json()["id"]
    resp = await client.delete(f"/api/notifications/channels/{channel_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/notifications/channels/{channel_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_channel_requires_auth(client):
    """Testing a channel should require authentication."""
    create = await client.post(
        "/api/notifications/channels/",
        json={"name": "Test Chan", "type": "slack", "config": {}},
    )
    channel_id = create.json()["id"]
    resp = await client.post(f"/api/notifications/channels/{channel_id}/test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_test_channel_authenticated(auth_client):
    """Authenticated channel test should succeed and redact secrets."""
    create = await auth_client.post(
        "/api/notifications/channels/",
        json={"name": "Redact Test", "type": "slack", "config": {"token": "secret-value"}},
    )
    channel_id = create.json()["id"]
    resp = await auth_client.post(f"/api/notifications/channels/{channel_id}/test")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert data["channel"]["config"]["token"] == "***"


# ── Incidents ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_incidents_empty(client):
    """Incidents list should be empty on a fresh database."""
    resp = await client.get("/api/notifications/incidents/")
    assert resp.status_code == 200
    assert resp.json() == []
