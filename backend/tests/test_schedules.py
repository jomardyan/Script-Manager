"""
Tests for the Schedule Jobs API endpoints.
"""
import pytest


@pytest.mark.asyncio
async def test_list_jobs_empty(client):
    """Jobs list should be empty on a fresh database."""
    resp = await client.get("/api/schedules/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_job_with_command(client):
    """Creating a job with a shell command should succeed."""
    resp = await client.post(
        "/api/schedules/",
        json={
            "name": "Daily Cleanup",
            "command": "echo 'cleanup'",
            "cron_expression": "0 2 * * *",
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Daily Cleanup"
    assert data["cron_expression"] == "0 2 * * *"


@pytest.mark.asyncio
async def test_create_job_requires_script_or_command(client):
    """Creating a job without script_id or command should return 400."""
    resp = await client.post(
        "/api/schedules/",
        json={"name": "Empty Job", "cron_expression": "* * * * *"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_job_duplicate_name(client):
    """Duplicate job names should return 400."""
    payload = {"name": "Dup Job", "command": "echo x", "cron_expression": "* * * * *"}
    await client.post("/api/schedules/", json=payload)
    resp = await client.post("/api/schedules/", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_job(client):
    """Getting a job by ID should return its data."""
    create = await client.post(
        "/api/schedules/",
        json={"name": "Fetch Job", "command": "echo hi", "cron_expression": "* * * * *"},
    )
    job_id = create.json()["id"]
    resp = await client.get(f"/api/schedules/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Fetch Job"


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    """Getting a non-existent job should return 404."""
    resp = await client.get("/api/schedules/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_job(client):
    """Updating a job should persist the change."""
    create = await client.post(
        "/api/schedules/",
        json={"name": "Old Job", "command": "echo old", "cron_expression": "* * * * *"},
    )
    job_id = create.json()["id"]
    resp = await client.put(f"/api/schedules/{job_id}", json={"name": "New Job"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Job"


@pytest.mark.asyncio
async def test_enable_disable_job(client):
    """Enabling and disabling a job should return a success message."""
    create = await client.post(
        "/api/schedules/",
        json={"name": "Toggle Job", "command": "echo toggle", "cron_expression": "* * * * *", "enabled": True},
    )
    job_id = create.json()["id"]

    resp = await client.post(f"/api/schedules/{job_id}/disable")
    assert resp.status_code == 200
    assert "disabled" in resp.json().get("message", "").lower()

    resp = await client.post(f"/api/schedules/{job_id}/enable")
    assert resp.status_code == 200
    assert "enabled" in resp.json().get("message", "").lower()


@pytest.mark.asyncio
async def test_delete_job(client):
    """Deleting a job should return 204 and remove it."""
    create = await client.post(
        "/api/schedules/",
        json={"name": "Delete Me", "command": "echo bye", "cron_expression": "* * * * *"},
    )
    job_id = create.json()["id"]
    resp = await client.delete(f"/api/schedules/{job_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/schedules/{job_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_executions_empty(client):
    """Execution history for a new job should be empty."""
    create = await client.post(
        "/api/schedules/",
        json={"name": "Exec History Job", "command": "echo hist", "cron_expression": "* * * * *"},
    )
    job_id = create.json()["id"]
    resp = await client.get(f"/api/schedules/{job_id}/executions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_job_metrics(client):
    """Job metrics endpoint should return a dict with job_id."""
    create = await client.post(
        "/api/schedules/",
        json={"name": "Metrics Job", "command": "echo metrics", "cron_expression": "* * * * *"},
    )
    job_id = create.json()["id"]
    resp = await client.get(f"/api/schedules/{job_id}/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert metrics["job_id"] == job_id
