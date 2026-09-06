"""
Tests for scheduling behaviour: validation, next-run computation, overlap
prevention and the background evaluator.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

import app.db.database as db_mod
from app.services import scheduler


async def _create_job(client, **overrides):
    payload = {
        "name": overrides.pop("name", "job"),
        "command": overrides.pop("command", "true"),
        "cron_expression": overrides.pop("cron_expression", "0 * * * *"),
        **overrides,
    }
    resp = await client.post("/api/schedules/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Validation ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_cron_is_rejected(client):
    """A garbage schedule used to be accepted with 201 and then never run."""
    resp = await client.post(
        "/api/schedules/",
        json={"name": "bad-cron", "command": "true", "cron_expression": "every tuesday"},
    )
    assert resp.status_code == 400
    assert "cron" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_timezone_is_rejected(client):
    resp = await client.post(
        "/api/schedules/",
        json={
            "name": "bad-tz", "command": "true",
            "cron_expression": "0 * * * *", "timezone": "Mars/Olympus_Mons",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zero_timeout_is_rejected(client):
    """timeout_seconds=0 silently meant 'no timeout' rather than 'fail fast'."""
    resp = await client.post(
        "/api/schedules/",
        json={"name": "zero", "command": "true", "cron_expression": "0 * * * *", "timeout_seconds": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_script_id_reports_the_real_reason(client):
    """This used to surface as the IntegrityError handler's 'name already exists'."""
    resp = await client.post(
        "/api/schedules/",
        json={"name": "ghost", "script_id": 9999, "cron_expression": "0 * * * *"},
    )
    assert resp.status_code == 404
    assert "Script" in resp.json()["detail"]


# ── next_run_at ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_next_run_is_computed_on_create(client):
    job = await _create_job(client, name="scheduled", cron_expression="*/5 * * * *")
    assert job["next_run_at"] is not None
    when = scheduler.parse_sqlite_timestamp(job["next_run_at"])
    assert when > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_disabling_clears_next_run(client):
    job = await _create_job(client, name="toggle")
    assert (await client.post(f"/api/schedules/{job['id']}/disable")).status_code == 200
    assert (await client.get(f"/api/schedules/{job['id']}")).json()["next_run_at"] is None

    enabled = await client.post(f"/api/schedules/{job['id']}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["next_run_at"] is not None


@pytest.mark.asyncio
async def test_cron_preview(client):
    resp = await client.get(
        "/api/schedules/preview/cron",
        params={"expression": "0 9 * * 1-5", "timezone": "UTC", "count": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["next_runs"]) == 3
    assert data["next_runs"] == sorted(data["next_runs"])


# ── Overlap prevention ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overlap_prevention_refuses_a_second_run(client):
    job = await _create_job(client, name="overlap", prevent_overlap=True)

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) "
            "VALUES (?, CURRENT_TIMESTAMP, 'running')",
            (job["id"],),
        )
        await db.commit()

    resp = await client.post(f"/api/schedules/{job['id']}/trigger")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_only_one_running_execution_can_exist(app):
    """
    The database enforces it, not just the application check.

    Overlap prevention was a check-then-act race: two concurrent triggers could
    both observe no running execution and both insert one.
    """
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO schedule_jobs (name, command, cron_expression) VALUES ('race', 'true', '0 * * * *')"
        )
        await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) VALUES (1, CURRENT_TIMESTAMP, 'running')"
        )
        await db.commit()

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO job_executions (job_id, started_at, status) "
                "VALUES (1, CURRENT_TIMESTAMP, 'running')"
            )
            await db.commit()


# ── Execution ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_job_execution_captures_output(app):
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO schedule_jobs (name, command, cron_expression) "
            "VALUES ('echo', 'echo hello', '0 * * * *')"
        )
        cursor = await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) "
            "VALUES (1, CURRENT_TIMESTAMP, 'running')"
        )
        execution_id = cursor.lastrowid
        await db.commit()

    await scheduler.run_job_execution(
        execution_id=execution_id, job_id=1, command="echo hello",
        timeout=30, max_retries=0, retry_delay=1, db_path=db_mod.DB_PATH,
    )

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM job_executions WHERE id = ?", (execution_id,)
        ) as cursor:
            row = await cursor.fetchone()

    assert row["status"] == "success"
    assert row["exit_code"] == 0
    assert "hello" in row["stdout"]


@pytest.mark.asyncio
async def test_failed_job_raises_an_incident(app):
    """A failing job used to leave no trace beyond its execution row."""
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO schedule_jobs (name, command, cron_expression) "
            "VALUES ('boom', 'exit 3', '0 * * * *')"
        )
        cursor = await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) "
            "VALUES (1, CURRENT_TIMESTAMP, 'running')"
        )
        execution_id = cursor.lastrowid
        await db.commit()

    await scheduler.run_job_execution(
        execution_id=execution_id, job_id=1, command="exit 3",
        timeout=30, max_retries=0, retry_delay=1, db_path=db_mod.DB_PATH,
    )

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM incidents WHERE source_type = 'schedule'"
        ) as cursor:
            incidents = await cursor.fetchall()

    assert len(incidents) == 1
    assert "boom" in incidents[0]["title"]


@pytest.mark.asyncio
async def test_timeout_kills_the_job(app):
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO schedule_jobs (name, command, cron_expression) "
            "VALUES ('slow', 'sleep 30', '0 * * * *')"
        )
        cursor = await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) "
            "VALUES (1, CURRENT_TIMESTAMP, 'running')"
        )
        execution_id = cursor.lastrowid
        await db.commit()

    await asyncio.wait_for(
        scheduler.run_job_execution(
            execution_id=execution_id, job_id=1, command="sleep 30",
            timeout=1, max_retries=0, retry_delay=1, db_path=db_mod.DB_PATH,
        ),
        # Generous, but far below the 30s the command asked for: the point is
        # that the killed process's pipes no longer block the drain forever.
        timeout=20,
    )

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM job_executions WHERE id = ?", (execution_id,)
        ) as cursor:
            row = await cursor.fetchone()

    assert row["status"] == "timeout"
    assert "TIMEOUT" in row["stderr"]


@pytest.mark.asyncio
async def test_stale_running_executions_are_reaped(app):
    """A restart mid-run used to deadlock overlap-protected jobs forever."""
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO schedule_jobs (name, command, cron_expression) "
            "VALUES ('stale', 'true', '0 * * * *')"
        )
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) VALUES (1, ?, 'running')",
            (old,),
        )
        await db.commit()

    assert await scheduler.reap_stale_executions(db_mod.DB_PATH) == 1

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        async with db.execute(
            "SELECT status FROM job_executions WHERE job_id = 1"
        ) as cursor:
            assert (await cursor.fetchone())[0] == "failed"


# ── Monitor evaluation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overdue_monitor_is_flagged_without_anyone_watching(client):
    """Detection used to happen only while somebody had the page open."""
    created = await client.post(
        "/api/monitors/",
        json={"name": "overdue", "expected_interval_seconds": 10, "grace_period_seconds": 0},
    )
    monitor_id = created.json()["id"]

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        await db.execute(
            "UPDATE monitors SET last_ping_at = ?, status = 'ok' WHERE id = ?",
            (stale, monitor_id),
        )
        await db.commit()

    assert await scheduler.tick_monitors(db_mod.DB_PATH) == 1

    detail = await client.get(f"/api/monitors/{monitor_id}")
    assert detail.json()["status"] == "failing"

    incidents = await client.get("/api/notifications/incidents/", params={"source_type": "monitor"})
    assert len(incidents.json()) == 1


@pytest.mark.asyncio
async def test_never_pinged_monitor_alerts_from_creation(client):
    """A cron job that never ran once should still raise an alert."""
    created = await client.post(
        "/api/monitors/",
        json={"name": "silent", "expected_interval_seconds": 10, "grace_period_seconds": 0},
    )
    monitor_id = created.json()["id"]

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await db.execute("UPDATE monitors SET created_at = ? WHERE id = ?", (old, monitor_id))
        await db.commit()

    assert await scheduler.tick_monitors(db_mod.DB_PATH) == 1
    assert (await client.get(f"/api/monitors/{monitor_id}")).json()["status"] == "failing"


@pytest.mark.asyncio
async def test_ping_recovers_the_monitor_and_resolves_its_incident(client):
    created = await client.post(
        "/api/monitors/",
        json={"name": "recovers", "expected_interval_seconds": 10, "grace_period_seconds": 0},
    )
    monitor = created.json()
    ping_key = monitor["ping_key"]

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        await db.execute(
            "UPDATE monitors SET last_ping_at = ?, status = 'ok' WHERE id = ?",
            (stale, monitor["id"]),
        )
        await db.commit()

    await scheduler.tick_monitors(db_mod.DB_PATH)

    ping = await client.post(f"/api/monitors/ping/{ping_key}")
    assert ping.status_code == 200
    assert ping.json()["recovered"] is True

    incidents = await client.get("/api/notifications/incidents/", params={"source_type": "monitor"})
    assert [i["status"] for i in incidents.json()] == ["resolved"]


@pytest.mark.asyncio
async def test_ping_key_is_not_exposed_in_listings(client):
    """The key is the credential a heartbeat needs; it should not be broadcast."""
    await client.post(
        "/api/monitors/", json={"name": "private", "expected_interval_seconds": 60}
    )

    listed = await client.get("/api/monitors/")
    assert listed.json()[0]["ping_key"] is None

    detail_id = listed.json()[0]["id"]
    assert (await client.get(f"/api/monitors/{detail_id}")).json()["ping_key"] is None

    revealed = await client.get(f"/api/monitors/{detail_id}/ping-url")
    assert revealed.status_code == 200
    assert revealed.json()["ping_key"]
