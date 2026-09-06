"""
Tests for data-layer behaviour that used to fail silently.
"""
import aiosqlite
import pytest

import app.db.database as db_mod


@pytest.mark.asyncio
async def test_request_connection_enables_foreign_keys(app):
    """
    Without `PRAGMA foreign_keys = ON` on the request connection every
    ON DELETE CASCADE in the schema is a no-op, which orphaned scripts,
    notes, tags, pings and executions.
    """
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        async with db.execute("PRAGMA foreign_keys") as cursor:
            assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_deleting_a_root_removes_its_scripts(client, tmp_path):
    created = await client.post(
        "/api/folder-roots/", json={"path": str(tmp_path), "name": "Cascade Root"}
    )
    root_id = created.json()["id"]

    # Insert a script directly: scanning an empty directory would find none.
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO scripts (root_id, path, name) VALUES (?, ?, ?)",
            (root_id, str(tmp_path / "a.py"), "a.py"),
        )
        await db.commit()

    listed = await client.get("/api/scripts/")
    assert listed.json()["total"] == 1

    assert (await client.delete(f"/api/folder-roots/{root_id}")).status_code == 200

    listed = await client.get("/api/scripts/")
    assert listed.json()["total"] == 0, "scripts survived their folder root"


@pytest.mark.asyncio
async def test_deleting_a_monitor_removes_its_pings(client):
    created = await client.post(
        "/api/monitors/", json={"name": "ping-cascade", "expected_interval_seconds": 60}
    )
    monitor = created.json()
    await client.post(f"/api/monitors/ping/{monitor['ping_key']}")

    assert (await client.delete(f"/api/monitors/{monitor['id']}")).status_code == 204

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        async with db.execute(
            "SELECT COUNT(*) FROM monitor_pings WHERE monitor_id = ?", (monitor["id"],)
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_deleting_a_job_removes_its_executions(client):
    created = await client.post(
        "/api/schedules/",
        json={"name": "exec-cascade", "command": "true", "cron_expression": "0 * * * *"},
    )
    job_id = created.json()["id"]

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        await db.execute(
            "INSERT INTO job_executions (job_id, started_at, status) "
            "VALUES (?, CURRENT_TIMESTAMP, 'success')",
            (job_id,),
        )
        await db.commit()

    assert (await client.delete(f"/api/schedules/{job_id}")).status_code == 204

    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        await db_mod.apply_connection_pragmas(db)
        async with db.execute(
            "SELECT COUNT(*) FROM job_executions WHERE job_id = ?", (job_id,)
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_cleanup_orphans_repairs_an_existing_database(app):
    """Databases written before foreign keys were enabled still hold orphans."""
    async with aiosqlite.connect(db_mod.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Deliberately leave foreign keys OFF to reproduce the old behaviour.
        cursor = await db.execute(
            "INSERT INTO folder_roots (path, name) VALUES ('/orphan-root', 'Orphan')"
        )
        root_id = cursor.lastrowid
        await db.execute(
            "INSERT INTO scripts (root_id, path, name) VALUES (?, '/orphan-root/a.py', 'a.py')",
            (root_id,),
        )
        await db.commit()
        await db.execute("DELETE FROM folder_roots WHERE id = ?", (root_id,))
        await db.commit()

        async with db.execute("SELECT COUNT(*) FROM scripts") as cur:
            assert (await cur.fetchone())[0] == 1, "expected an orphan to repair"

        removed = await db_mod.cleanup_orphans(db)
        assert removed.get("scripts") == 1

        async with db.execute("SELECT COUNT(*) FROM scripts") as cur:
            assert (await cur.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_migration_adds_missing_columns(tmp_path, monkeypatch):
    """A database from an older release must gain new columns, not stay stale."""
    db_path = str(tmp_path / "legacy.db")
    async with aiosqlite.connect(db_path) as db:
        # Minimal legacy shape: no next_run_at column.
        await db.execute(
            """
            CREATE TABLE schedule_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                cron_expression TEXT NOT NULL
            )
            """
        )
        await db.commit()

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    await db_mod.init_db()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(schedule_jobs)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
    assert "next_run_at" in columns
    assert "notify_channel_ids" in columns
