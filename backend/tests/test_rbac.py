"""
Tests that the RBAC model is actually enforced by the API.

The permission model existed for a long time without any endpoint consulting
it, so these tests pin down that anonymous callers are refused and that a
read-only viewer cannot mutate anything.
"""
import pytest

# (method, path) pairs that must never be reachable without credentials.
PROTECTED_READS = [
    "/api/scripts/",
    "/api/tags/",
    "/api/folder-roots/",
    "/api/search/stats",
    "/api/monitors/",
    "/api/schedules/",
    "/api/notifications/channels/",
    "/api/notifications/incidents/",
    "/api/auth/users",
    "/api/auth/roles",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PROTECTED_READS)
async def test_anonymous_reads_are_refused(anon_client, path):
    resp = await anon_client.get(path)
    assert resp.status_code == 401, f"{path} was reachable anonymously"


@pytest.mark.asyncio
async def test_anonymous_writes_are_refused(anon_client):
    resp = await anon_client.post("/api/tags/", json={"name": "sneaky"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_is_refused(anon_client):
    anon_client.headers.update({"Authorization": "Bearer not-a-real-token"})
    resp = await anon_client.get("/api/tags/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_viewer_can_read(viewer_client):
    resp = await viewer_client.get("/api/tags/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_viewer_cannot_create_tags(viewer_client):
    resp = await viewer_client.post("/api/tags/", json={"name": "viewer-tag"})
    assert resp.status_code == 403
    assert "tags.create" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_viewer_cannot_manage_users(viewer_client):
    resp = await viewer_client.get("/api/auth/users")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_trigger_jobs(viewer_client, client):
    created = await client.post(
        "/api/schedules/",
        json={"name": "viewer-blocked", "command": "echo hi", "cron_expression": "0 * * * *"},
    )
    job_id = created.json()["id"]
    resp = await viewer_client.post(f"/api/schedules/{job_id}/trigger")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_monitor_ping_stays_public(anon_client, client):
    """A cron job holds only the ping key, so the ping endpoint must be open."""
    created = await client.post(
        "/api/monitors/", json={"name": "public-ping", "expected_interval_seconds": 60}
    )
    ping_key = created.json()["ping_key"]
    resp = await anon_client.post(f"/api/monitors/ping/{ping_key}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_and_setup_status_stay_public(anon_client):
    assert (await anon_client.get("/health")).status_code == 200
    assert (await anon_client.get("/api/setup/status")).status_code == 200
    assert (await anon_client.get("/api/auth/config")).status_code == 200


@pytest.mark.asyncio
async def test_self_registration_disabled_by_default(anon_client):
    resp = await anon_client.post(
        "/api/auth/register",
        json={"username": "stranger", "email": "s@example.com", "password": "Password123"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_last_admin_cannot_be_deleted_or_demoted(client):
    users = (await client.get("/api/auth/users")).json()
    admin = next(u for u in users if u["username"] == "testadmin")

    demote = await client.put(
        f"/api/auth/users/{admin['id']}", json={"is_active": False}
    )
    assert demote.status_code == 400
    assert "last administrator" in demote.json()["detail"]

    deleted = await client.delete(f"/api/auth/users/{admin['id']}")
    # Deleting yourself is refused before the last-admin check even applies.
    assert deleted.status_code == 400


@pytest.mark.asyncio
async def test_change_password_uses_request_body(client):
    """Credentials must not have to travel in the query string."""
    resp = await client.put(
        "/api/auth/change-password",
        json={"old_password": "TestPass123!", "new_password": "BrandNewPass9"},
    )
    assert resp.status_code == 200

    relogin = await client.post(
        "/api/auth/login",
        data={"username": "testadmin", "password": "BrandNewPass9"},
    )
    assert relogin.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_weak_password(client):
    resp = await client.put(
        "/api/auth/change-password",
        json={"old_password": "TestPass123!", "new_password": "short"},
    )
    assert resp.status_code == 422  # below the schema's minimum length


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_old_password(client):
    resp = await client.put(
        "/api/auth/change-password",
        json={"old_password": "not-the-password", "new_password": "BrandNewPass9"},
    )
    assert resp.status_code == 400
