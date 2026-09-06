"""
Schedule Jobs API endpoints

Provides CRUD for cron-scheduled tasks with:
 - Timezone-aware cron expressions, validated on write and executed by the
   in-process scheduler (app.services.scheduler)
 - Overlap prevention (locking)
 - Auto-retry on failure
 - Full execution log capture (stdout/stderr)
 - Performance metrics
 - Zombie/anomaly duration detection
"""
import json
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.db.database import get_db, DB_PATH
from app.models.schemas import (
    ScheduleJobCreate, ScheduleJobResponse, ScheduleJobUpdate,
    JobExecutionResponse,
)
from app.routes.deps import require_permission
from app.services.cron import CronError, describe, validate_cron, validate_timezone
from app.services import scheduler

router = APIRouter()

read_access = Depends(require_permission("schedules.read"))
write_access = Depends(require_permission("schedules.update"))
run_access = Depends(require_permission("schedules.run"))
delete_access = Depends(require_permission("schedules.delete"))


def _parse_channel_ids(raw: Optional[str]) -> List[int]:
    return scheduler.parse_channel_ids(raw)


def _job_from_row(row) -> dict:
    d = dict(row)
    d["notify_channel_ids"] = _parse_channel_ids(d.get("notify_channel_ids"))
    return d


def _validate_schedule(cron_expression: str, tz_name: str) -> str:
    """Validate a cron expression + timezone pair, returning the timezone name."""
    try:
        validate_cron(cron_expression)
        return validate_timezone(tz_name)
    except CronError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def _next_run_for(cron_expression: str, tz_name: str) -> Optional[str]:
    return await scheduler.compute_next_run(cron_expression, tz_name)


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ScheduleJobResponse], dependencies=[read_access])
async def list_jobs(db: aiosqlite.Connection = Depends(get_db)):
    """List all scheduled jobs."""
    async with db.execute("SELECT * FROM schedule_jobs ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [_job_from_row(r) for r in rows]


@router.post("/", response_model=ScheduleJobResponse, status_code=201,
             dependencies=[Depends(require_permission("schedules.create"))])
async def create_job(data: ScheduleJobCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new scheduled job."""
    if not data.script_id and not data.command:
        raise HTTPException(
            status_code=400, detail="Either script_id or command must be provided"
        )
    if data.script_id is not None:
        # Checked up front so a bad script id does not surface as the
        # IntegrityError handler's "Job name already exists".
        async with db.execute("SELECT id FROM scripts WHERE id = ?", (data.script_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Script not found")
    tz_name = _validate_schedule(data.cron_expression, data.timezone)
    next_run = await _next_run_for(data.cron_expression, tz_name)
    channel_ids_json = json.dumps(data.notify_channel_ids)
    try:
        cur = await db.execute(
            """
            INSERT INTO schedule_jobs
                (name, description, script_id, command, cron_expression, timezone,
                 enabled, max_retries, retry_delay_seconds, prevent_overlap,
                 timeout_seconds, notify_channel_ids, next_run_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.name, data.description, data.script_id, data.command,
                data.cron_expression, tz_name, int(data.enabled),
                data.max_retries, data.retry_delay_seconds,
                int(data.prevent_overlap), data.timeout_seconds,
                channel_ids_json, next_run if data.enabled else None,
            ),
        )
        job_id = cur.lastrowid
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Job name already exists")

    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    return _job_from_row(row)


@router.get("/{job_id}", response_model=ScheduleJobResponse, dependencies=[read_access])
async def get_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single scheduled job."""
    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_from_row(row)


@router.put("/{job_id}", response_model=ScheduleJobResponse, dependencies=[write_access])
async def update_job(
    job_id: int, data: ScheduleJobUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    """Update a scheduled job's configuration."""
    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        existing = await cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    # The schedule must stay valid as a pair, so validate the resulting values
    # rather than only the fields that were supplied.
    cron_expression = data.cron_expression if data.cron_expression is not None else existing["cron_expression"]
    tz_name = data.timezone if data.timezone is not None else existing["timezone"]
    tz_name = _validate_schedule(cron_expression, tz_name)

    if data.script_id is not None:
        async with db.execute("SELECT id FROM scripts WHERE id = ?", (data.script_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Script not found")

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
        fields.append("timezone = ?"); params.append(tz_name)
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

    enabled = data.enabled if data.enabled is not None else bool(existing["enabled"])
    fields.append("next_run_at = ?")
    params.append(await _next_run_for(cron_expression, tz_name) if enabled else None)

    fields.append("updated_at = CURRENT_TIMESTAMP")
    params.append(job_id)
    try:
        await db.execute(
            f"UPDATE schedule_jobs SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Job name already exists")

    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    return _job_from_row(row)


@router.delete("/{job_id}", status_code=204, dependencies=[delete_access])
async def delete_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a scheduled job and all its execution history."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
    await db.execute("DELETE FROM schedule_jobs WHERE id = ?", (job_id,))
    await db.execute(
        "DELETE FROM incidents WHERE source_type = 'schedule' AND source_id = ?", (job_id,)
    )
    await db.commit()


# ── Schedule preview ──────────────────────────────────────────────────────────

@router.get("/preview/cron", dependencies=[read_access])
async def preview_cron(
    expression: str = Query(..., description="5-field cron expression"),
    timezone_name: str = Query("UTC", alias="timezone"),
    count: int = Query(5, ge=1, le=20),
):
    """
    Validate a cron expression and return the next few run times.

    Lets the UI show a user what their schedule actually means before saving.
    """
    try:
        validate_cron(expression)
        tz_name = validate_timezone(timezone_name)
    except CronError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    runs = []
    cursor_time = datetime.now(timezone.utc)
    for _ in range(count):
        from app.services.cron import next_run_utc
        nxt = next_run_utc(expression, tz_name, cursor_time)
        if nxt is None:
            break
        runs.append(nxt.isoformat())
        cursor_time = nxt

    return {
        "expression": expression,
        "timezone": tz_name,
        "description": describe(expression),
        "next_runs": runs,
    }


# ── Enable / Disable ──────────────────────────────────────────────────────────

@router.post("/{job_id}/enable", dependencies=[write_access])
async def enable_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Enable a paused/disabled job."""
    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    next_run = await _next_run_for(row["cron_expression"], row["timezone"])
    await db.execute(
        "UPDATE schedule_jobs SET enabled = 1, next_run_at = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (next_run, job_id),
    )
    await db.commit()
    return {"message": "Job enabled", "next_run_at": next_run}


@router.post("/{job_id}/disable", dependencies=[write_access])
async def disable_job(job_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Disable (pause) a job without deleting it."""
    async with db.execute("SELECT id FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
    await db.execute(
        "UPDATE schedule_jobs SET enabled = 0, next_run_at = NULL, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,),
    )
    await db.commit()
    return {"message": "Job disabled"}


# ── Manual trigger ────────────────────────────────────────────────────────────

@router.post("/{job_id}/trigger", dependencies=[run_access])
async def trigger_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Manually trigger a job immediately (outside its cron schedule).
    The execution runs in the background; the endpoint returns the new
    execution ID so the caller can poll for logs.
    """
    async with db.execute("SELECT * FROM schedule_jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _job_from_row(row)

    # Resolve command: prefer explicit command, fall back to script path
    command = job.get("command") or ""
    if not command and job.get("script_id"):
        async with db.execute(
            "SELECT path FROM scripts WHERE id = ?", (job["script_id"],)
        ) as cur:
            script_row = await cur.fetchone()
        if script_row:
            command = script_row[0]
    if not command:
        raise HTTPException(
            status_code=400,
            detail="Job has no command and no resolvable script path",
        )

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

    try:
        cur2 = await db.execute(
            """
            INSERT INTO job_executions (job_id, started_at, status, triggered_by)
            VALUES (?, ?, 'running', 'manual')
            """,
            (job_id, datetime.now(timezone.utc).isoformat()),
        )
        execution_id = cur2.lastrowid
        await db.commit()
    except aiosqlite.IntegrityError:
        # The partial unique index on running executions rejected this insert,
        # which means another trigger won the race a moment ago.
        raise HTTPException(
            status_code=409,
            detail="Job is already running. Overlap prevention is enabled.",
        )

    background_tasks.add_task(
        scheduler.run_job_execution,
        execution_id=execution_id,
        job_id=job_id,
        command=command,
        timeout=job.get("timeout_seconds"),
        max_retries=job.get("max_retries", 0),
        retry_delay=job.get("retry_delay_seconds", 60),
        db_path=DB_PATH,
    )
    return {"message": "Job triggered", "execution_id": execution_id}


# ── Executions ────────────────────────────────────────────────────────────────

@router.get("/{job_id}/executions", response_model=List[JobExecutionResponse],
            dependencies=[read_access])
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
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        (job_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{job_id}/executions/{execution_id}", response_model=JobExecutionResponse,
            dependencies=[read_access])
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


@router.get("/{job_id}/metrics", dependencies=[read_access])
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
            SUM(CASE WHEN status IN ('failed', 'timeout') THEN 1 ELSE 0 END) AS failed,
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

    async with db.execute(
        """
        SELECT
            COUNT(*) AS total_runs,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successful,
            AVG(duration_seconds) AS avg_duration
        FROM job_executions
        WHERE job_id = ? AND status != 'running'
          AND started_at >= DATE('now', ? || ' days')
        """,
        (job_id, f"-{days}"),
    ) as cur:
        summary_row = await cur.fetchone()

    summary = dict(summary_row) if summary_row else {}
    total = summary.get("total_runs") or 0
    successful = summary.get("successful") or 0
    summary["success_rate"] = round((successful / total) * 100, 1) if total else None

    return {
        "job_id": job_id,
        "days": days,
        "summary": summary,
        "data": [dict(r) for r in rows],
    }
