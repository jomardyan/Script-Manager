"""
Schedule Jobs API endpoints

Provides CRUD for cron-scheduled tasks with:
 - Timezone-aware cron expressions
 - Overlap prevention (locking)
 - Auto-retry on failure
 - Full execution log capture (stdout/stderr)
 - Performance metrics
"""
import json
import subprocess
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query

from app.db.database import get_db, DB_PATH
from app.models.schemas import (
    ScheduleJobCreate, ScheduleJobResponse, ScheduleJobUpdate,
    JobExecutionResponse,
)

router = APIRouter()


def _parse_channel_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _job_from_row(row) -> dict:
    d = dict(row)
    d["notify_channel_ids"] = _parse_channel_ids(d.get("notify_channel_ids"))
    return d


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ScheduleJobResponse])
async def list_jobs(db: aiosqlite.Connection = Depends(get_db)):
    """List all scheduled jobs."""
    async with db.execute("SELECT * FROM schedule_jobs ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [_job_from_row(r) for r in rows]


@router.post("/", response_model=ScheduleJobResponse, status_code=201)
async def create_job(data: ScheduleJobCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new scheduled job."""
    if not data.script_id and not data.command:
        raise HTTPException(
            status_code=400, detail="Either script_id or command must be provided"
        )
    channel_ids_json = json.dumps(data.notify_channel_ids)
    try:
        cur = await db.execute(
            """
            INSERT INTO schedule_jobs
                (name, description, script_id, command, cron_expression, timezone,
                 enabled, max_retries, retry_delay_seconds, prevent_overlap,
                 timeout_seconds, notify_channel_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.name, data.description, data.script_id, data.command,
                data.cron_expression, data.timezone, int(data.enabled),
                data.max_retries, data.retry_delay_seconds,
                int(data.prevent_overlap), data.timeout_seconds,
                channel_ids_json,
            ),
        )
        job_id = cur.lastrowid
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Job name already exists")

    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    return _job_from_row(row)


@router.get("/{job_id}", response_model=ScheduleJobResponse)
async def get_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single scheduled job."""
    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_from_row(row)


@router.put("/{job_id}", response_model=ScheduleJobResponse)
async def update_job(
    job_id: int, data: ScheduleJobUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    """Update a scheduled job's configuration."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")

    fields, params = [], []
    if data.name is not None:
        fields.append("name = ?"); params.append(data.name)
    if data.description is not None:
        fields.append("description = ?"); params.append(data.description)
    if data.script_id is not None:
        fields.append("script_id = ?"); params.append(data.script_id)
    if data.command is not None:
        fields.append("command = ?"); params.append(data.command)
    if data.cron_expression is not None:
        fields.append("cron_expression = ?"); params.append(data.cron_expression)
    if data.timezone is not None:
        fields.append("timezone = ?"); params.append(data.timezone)
    if data.enabled is not None:
        fields.append("enabled = ?"); params.append(int(data.enabled))
    if data.max_retries is not None:
        fields.append("max_retries = ?"); params.append(data.max_retries)
    if data.retry_delay_seconds is not None:
        fields.append("retry_delay_seconds = ?"); params.append(data.retry_delay_seconds)
    if data.prevent_overlap is not None:
        fields.append("prevent_overlap = ?"); params.append(int(data.prevent_overlap))
    if data.timeout_seconds is not None:
        fields.append("timeout_seconds = ?"); params.append(data.timeout_seconds)
    if data.notify_channel_ids is not None:
        fields.append("notify_channel_ids = ?"); params.append(json.dumps(data.notify_channel_ids))

    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(job_id)
        await db.execute(
            f"UPDATE schedule_jobs SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()

    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    return _job_from_row(row)


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a scheduled job and all its execution history."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
    await db.execute("DELETE FROM schedule_jobs WHERE id = ?", (job_id,))
    await db.commit()


# ── Enable / Disable ──────────────────────────────────────────────────────────

@router.post("/{job_id}/enable")
async def enable_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Enable a paused/disabled job."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
    await db.execute(
        "UPDATE schedule_jobs SET enabled = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,),
    )
    await db.commit()
    return {"message": "Job enabled"}


@router.post("/{job_id}/disable")
async def disable_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Disable (pause) a job without deleting it."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
    await db.execute(
        "UPDATE schedule_jobs SET enabled = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,),
    )
    await db.commit()
    return {"message": "Job disabled"}


# ── Manual trigger ────────────────────────────────────────────────────────────

@router.post("/{job_id}/trigger")
async def trigger_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Manually trigger a job immediately (outside its cron schedule).
    The execution runs in the background; the endpoint returns the new execution ID.
    """
    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _job_from_row(row)

    # Check overlap prevention
    if job["prevent_overlap"]:
        async with db.execute(
            "SELECT id FROM job_executions WHERE job_id = ? AND status = 'running'",
            (job_id,),
        ) as cur:
            running = await cur.fetchone()
        if running:
            raise HTTPException(
                status_code=409,
                detail="Job is already running. Overlap prevention is enabled.",
            )

    # Create execution record
    cur2 = await db.execute(
        """
        INSERT INTO job_executions (job_id, started_at, status, triggered_by)
        VALUES (?, CURRENT_TIMESTAMP, 'running', 'manual')
        """,
        (job_id,),
    )
    execution_id = cur2.lastrowid
    await db.commit()

    # Run in background
    command = job.get("command") or ""
    background_tasks.add_task(
        _run_job_execution,
        execution_id=execution_id,
        job_id=job_id,
        command=command,
        timeout=job.get("timeout_seconds"),
        max_retries=job.get("max_retries", 0),
        retry_delay=job.get("retry_delay_seconds", 60),
    )
    return {"message": "Job triggered", "execution_id": execution_id}


# ── Executions ────────────────────────────────────────────────────────────────

@router.get("/{job_id}/executions", response_model=List[JobExecutionResponse])
async def list_executions(
    job_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List recent executions for a job (most recent first)."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
    async with db.execute(
        """
        SELECT * FROM job_executions
        WHERE job_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (job_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{job_id}/executions/{execution_id}", response_model=JobExecutionResponse)
async def get_execution(
    job_id: int,
    execution_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get details (including stdout/stderr logs) for a specific execution."""
    async with db.execute(
        "SELECT * FROM job_executions WHERE id = ? AND job_id = ?",
        (execution_id, job_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Execution not found")
    return dict(row)


@router.get("/{job_id}/metrics")
async def get_job_metrics(
    job_id: int,
    days: int = Query(30, ge=1, le=365),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return execution duration metrics for graphing performance trends."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")

    async with db.execute(
        """
        SELECT
            DATE(started_at) AS run_date,
            COUNT(*) AS total_runs,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successful,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            AVG(duration_seconds) AS avg_duration,
            MAX(duration_seconds) AS max_duration,
            MIN(duration_seconds) AS min_duration
        FROM job_executions
        WHERE job_id = ?
          AND started_at >= DATE('now', ? || ' days')
          AND status != 'running'
        GROUP BY DATE(started_at)
        ORDER BY run_date ASC
        """,
        (job_id, f"-{days}"),
    ) as cur:
        rows = await cur.fetchall()

    return {
        "job_id": job_id,
        "days": days,
        "data": [dict(r) for r in rows],
    }


# ── Background execution helper ───────────────────────────────────────────────

async def _run_job_execution(
    execution_id: int,
    job_id: int,
    command: str,
    timeout: Optional[int],
    max_retries: int,
    retry_delay: int,
):
    """Run the command in a subprocess, capture output, record result."""
    attempt = 0
    while True:
        started_at = datetime.now(timezone.utc)
        stdout_data, stderr_data = "", ""
        exit_code = None
        status = "failed"

        try:
            if not command:
                raise ValueError("No command to execute")

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                raw_out, raw_err = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout) if timeout else None
                )
            except asyncio.TimeoutError:
                proc.kill()
                raw_out, raw_err = await proc.communicate()
                stdout_data = raw_out.decode("utf-8", errors="replace")
                stderr_data = raw_err.decode("utf-8", errors="replace") + "\nTIMEOUT: process killed after timeout\n"
                exit_code = -1
            else:
                stdout_data = raw_out.decode("utf-8", errors="replace")
                stderr_data = raw_err.decode("utf-8", errors="replace")
                exit_code = proc.returncode

            status = "success" if exit_code == 0 else "failed"
        except Exception as exc:
            stderr_data += f"\nExecution error: {exc}"
            exit_code = -1
            status = "failed"

        ended_at = datetime.now(timezone.utc)
        duration = (ended_at - started_at).total_seconds()

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if attempt == 0:
                # Update the pre-created execution record
                await db.execute(
                    """
                    UPDATE job_executions
                    SET ended_at = ?, status = ?, exit_code = ?,
                        stdout = ?, stderr = ?, duration_seconds = ?,
                        retry_attempt = ?
                    WHERE id = ?
                    """,
                    (
                        ended_at.isoformat(), status, exit_code,
                        stdout_data, stderr_data, duration,
                        attempt, execution_id,
                    ),
                )
            else:
                # Insert a new record for the retry attempt
                await db.execute(
                    """
                    INSERT INTO job_executions
                        (job_id, started_at, ended_at, status, exit_code,
                         stdout, stderr, duration_seconds, retry_attempt, triggered_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'retry')
                    """,
                    (
                        job_id, started_at.isoformat(), ended_at.isoformat(),
                        status, exit_code, stdout_data, stderr_data, duration, attempt,
                    ),
                )

            # Update job's last_run_at and last_status
            await db.execute(
                """
                UPDATE schedule_jobs
                SET last_run_at = CURRENT_TIMESTAMP, last_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, job_id),
            )
            await db.commit()

        if status == "success" or attempt >= max_retries:
            break

        attempt += 1
        await asyncio.sleep(retry_delay)
