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
        json={
            "name": "My Slack",
            "type": "slack",
            "config": {"webhook_url": "https://hooks.slack.com/services/T000/B000/XXX"},
            "enabled": True,
        },
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
        json={
            "name": "Discord Alert",
            "type": "discord",
            "config": {"webhook_url": "https://discord.com/api/webhooks/1/abc"},
        },
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
        json={
            "name": "Old Name",
            "type": "email",
            "config": {"smtp_host": "smtp.example.com", "to": "ops@example.com"},
        },
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
        json={
            "name": "To Delete",
            "type": "webhook",
            "config": {"url": "https://example.com/hook"},
        },
    )
    channel_id = create.json()["id"]
    resp = await client.delete(f"/api/notifications/channels/{channel_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/notifications/channels/{channel_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_channel_requires_auth(client, anon_client):
    """Testing a channel should require authentication."""
    create = await client.post(
        "/api/notifications/channels/",
        json={
            "name": "Test Chan",
            "type": "slack",
            "config": {"webhook_url": "https://hooks.slack.com/services/T/B/X"},
        },
    )
    channel_id = create.json()["id"]
    resp = await anon_client.post(f"/api/notifications/channels/{channel_id}/test")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_test_channel_authenticated(auth_client):
    """Authenticated channel test should report an outcome and redact secrets."""
    create = await auth_client.post(
        "/api/notifications/channels/",
        json={
            "name": "Redact Test",
            "type": "slack",
            "config": {
                # Unroutable host: delivery fails fast without touching the network.
                "webhook_url": "http://127.0.0.1:1/slack",
                "token": "secret-value",
            },
        },
    )
    channel_id = create.json()["id"]
    resp = await auth_client.post(f"/api/notifications/channels/{channel_id}/test")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    # A delivery failure is reported in-band, not as an HTTP error.
    assert data["success"] is False
    assert data["channel"]["config"]["token"] == "***"
    assert data["channel"]["config"]["webhook_url"] == "***"


@pytest.mark.asyncio
async def test_channel_secrets_never_returned(client):
    """Secret config values must be redacted in list and get responses."""
    await client.post(
        "/api/notifications/channels/",
        json={
            "name": "Secret Slack",
            "type": "slack",
            "config": {"webhook_url": "https://hooks.slack.com/services/TOP/SECRET/VALUE"},
        },
    )
    listed = await client.get("/api/notifications/channels/")
    assert listed.status_code == 200
    assert listed.json()[0]["config"]["webhook_url"] == "***"


@pytest.mark.asyncio
async def test_create_channel_rejects_unusable_config(client):
    """A channel that could never deliver should be rejected at creation."""
    resp = await client.post(
        "/api/notifications/channels/",
        json={"name": "No Webhook", "type": "slack", "config": {}},
    )
    assert resp.status_code == 400
    assert "webhook_url" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_channel_keeps_redacted_secret(client):
    """Re-submitting the redaction placeholder must not wipe the stored secret."""
    real_url = "https://hooks.slack.com/services/KEEP/THIS/VALUE"
    create = await client.post(
        "/api/notifications/channels/",
        json={"name": "Keep Secret", "type": "slack", "config": {"webhook_url": real_url}},
    )
    channel_id = create.json()["id"]

    # This is exactly what the UI round-trips after a redacted read.
    resp = await client.put(
        f"/api/notifications/channels/{channel_id}",
        json={"name": "Renamed", "config": {"webhook_url": "***"}},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"

    test_resp = await client.post(f"/api/notifications/channels/{channel_id}/test")
    # Delivery is attempted against the preserved URL rather than failing
    # validation, which is what would happen if the secret had been erased.
    assert "webhook_url" not in (test_resp.json().get("message") or "")


# ── Incidents ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_incidents_empty(client):
    """Incidents list should be empty on a fresh database."""
    resp = await client.get("/api/notifications/incidents/")
    assert resp.status_code == 200
    assert resp.json() == []
