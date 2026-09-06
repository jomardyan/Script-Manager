"""
Background scheduler and monitor evaluator.

Two responsibilities, both previously missing:

  * **Job scheduler** - jobs stored a ``cron_expression`` but nothing ever ran
    them, so "scheduled" jobs only executed when a human clicked Run. This loop
    computes ``next_run_at`` and fires jobs when they come due.
  * **Monitor evaluator** - heartbeat monitors only re-evaluated their status
    while somebody had the Monitors page open, so an overdue cron job produced
    no incident and no alert unless a browser happened to be watching. This
    loop evaluates them on a timer.

Both loops are resilient: an exception in one tick is logged and the loop
continues. Set ``ENABLE_SCHEDULER=false`` to disable them (the test suite and
read-only replicas do).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiosqlite

from app.db import database as db_module
from app.services import notifier
from app.services.cron import CronError, next_run_utc

logger = logging.getLogger(__name__)

TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "30"))
# A job whose next_run_at slipped further into the past than this is rescheduled
# rather than fired, so a backend that was offline for a week does not stampede.
MAX_CATCHUP_SECONDS = int(os.getenv("SCHEDULER_MAX_CATCHUP_SECONDS", "3600"))
# Captured stdout/stderr is stored in SQLite; cap it so one chatty job cannot
# bloat the database.
MAX_LOG_CHARS = int(os.getenv("JOB_LOG_MAX_CHARS", "200000"))
# How long to wait for a killed job's pipes to close before giving up on them.
KILL_DRAIN_SECONDS = 10.0


def scheduler_enabled() -> bool:
    return os.getenv("ENABLE_SCHEDULER", "true").strip().lower() not in ("0", "false", "no", "off")


def _kill_process_group(proc) -> None:
    """Terminate a job's whole process group, falling back to the process."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _truncate(text: str) -> str:
    if text and len(text) > MAX_LOG_CHARS:
        return text[:MAX_LOG_CHARS] + f"\n... [truncated, {len(text) - MAX_LOG_CHARS} more characters]"
    return text


def parse_channel_ids(raw) -> List[int]:
    """Parse the JSON-encoded notify_channel_ids column into a list of ints."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [int(v) for v in raw]
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def parse_sqlite_timestamp(value) -> Optional[datetime]:
    """
    Parse a SQLite timestamp into an aware UTC datetime.

    SQLite's CURRENT_TIMESTAMP writes naive UTC strings ("YYYY-MM-DD HH:MM:SS"),
    while code paths that store ``datetime.isoformat()`` write offset-aware
    ones. Both must compare correctly against ``datetime.now(timezone.utc)``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def compute_next_run(cron_expression: str, tz_name: str = "UTC",
                           after: Optional[datetime] = None) -> Optional[str]:
    """Return the next run time as an ISO-8601 UTC string, or None."""
    try:
        moment = next_run_utc(cron_expression, tz_name, after)
    except CronError:
        return None
    return moment.isoformat() if moment else None


# ── Job execution ─────────────────────────────────────────────────────────────

async def run_job_execution(
    execution_id: int,
    job_id: int,
    command: str,
    timeout: Optional[int],
    max_retries: int,
    retry_delay: int,
    db_path: Optional[str] = None,
):
    """
    Run a job's command in a subprocess, capture output, record the result and
    alert the job's notification channels when it ultimately fails.

    Retries create additional execution rows so the history shows every attempt.
    """
    db_path = db_path or db_module.DB_PATH
    attempt = 0
    final_status = "failed"
    final_stderr = ""

    while True:
        started_at = datetime.now(timezone.utc)
        stdout_data, stderr_data = "", ""
        exit_code: Optional[int] = None
        status = "failed"

        try:
            if not command:
                raise ValueError("No command to execute")

            # start_new_session puts the shell and everything it spawns in one
            # process group, so a timeout can kill the children too. Killing
            # only the shell left the real workload running and the subsequent
            # drain of its still-open pipes blocked forever.
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                raw_out, raw_err = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout) if timeout else None
                )
            except asyncio.TimeoutError:
                _kill_process_group(proc)
                try:
                    raw_out, raw_err = await asyncio.wait_for(
                        proc.communicate(), timeout=KILL_DRAIN_SECONDS
                    )
                except asyncio.TimeoutError:
                    raw_out, raw_err = b"", b""
                stdout_data = raw_out.decode("utf-8", errors="replace")
                stderr_data = (
                    raw_err.decode("utf-8", errors="replace")
                    + f"\nTIMEOUT: process group killed after {timeout}s\n"
                )
                exit_code = -1
                status = "timeout"
            else:
                stdout_data = raw_out.decode("utf-8", errors="replace")
                stderr_data = raw_err.decode("utf-8", errors="replace")
                exit_code = proc.returncode
                status = "success" if exit_code == 0 else "failed"
        except Exception as exc:  # noqa: BLE001 - the failure belongs in the log row
            stderr_data += f"\nExecution error: {exc}"
            exit_code = -1
            status = "failed"

        ended_at = datetime.now(timezone.utc)
        duration = (ended_at - started_at).total_seconds()
        stdout_data = _truncate(stdout_data)
        stderr_data = _truncate(stderr_data)
        final_status, final_stderr = status, stderr_data

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db_module.apply_connection_pragmas(db)
            current_exec_id = execution_id
            if attempt == 0:
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
                        stdout_data, stderr_data, duration, attempt, execution_id,
                    ),
                )
            else:
                retry_cur = await db.execute(
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
                current_exec_id = retry_cur.lastrowid

            await db.execute(
                """
                UPDATE schedule_jobs
                SET last_run_at = ?, last_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (ended_at.isoformat(), status, job_id),
            )
            await db.commit()

        if attempt == 0 and status not in ("running", "timeout") and duration is not None:
            await check_zombie_duration(job_id, duration, current_exec_id, db_path)

        if status == "success" or attempt >= max_retries:
            break

        attempt += 1
        await asyncio.sleep(retry_delay)

    if final_status != "success":
        await _alert_job_failure(job_id, final_status, final_stderr, db_path)
    else:
        # A recovered job should not leave a stale open incident behind.
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db_module.apply_connection_pragmas(db)
            await resolve_job_incidents(db, job_id)
            await db.commit()


async def _alert_job_failure(job_id: int, status: str, stderr: str, db_path: str):
    """Open an incident for a failed job and notify its channels."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db_module.apply_connection_pragmas(db)
            async with db.execute(
                "SELECT name, notify_channel_ids FROM schedule_jobs WHERE id = ?", (job_id,)
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return
            job_name = row["name"]
            channel_ids = parse_channel_ids(row["notify_channel_ids"])

            title = f"Scheduled job '{job_name}' {status}"
            description = (stderr or "").strip()[:2000] or f"Job finished with status '{status}'."

            async with db.execute(
                """
                SELECT id FROM incidents
                WHERE source_type = 'schedule' AND source_id = ? AND status = 'open'
                  AND title = ?
                """,
                (job_id, title),
            ) as cursor:
                existing = await cursor.fetchone()

            if not existing:
                await db.execute(
                    """
                    INSERT INTO incidents (title, source_type, source_id, status, severity, description)
                    VALUES (?, 'schedule', ?, 'open', 'critical', ?)
                    """,
                    (title, job_id, description),
                )
                await db.commit()

            if channel_ids:
                await notifier.dispatch(
                    db,
                    channel_ids,
                    notifier.Alert(
                        title=title,
                        body=description,
                        severity="critical",
                        source="script-manager/schedules",
                    ),
                )
    except Exception as exc:  # noqa: BLE001 - alerting must never break execution
        logger.warning("Could not raise failure alert for job %s: %s", job_id, exc)


async def check_zombie_duration(job_id: int, current_duration: float,
                                execution_id: int, db_path: Optional[str] = None):
    """
    Compare a run's duration against its historical average and open a
    'zombie' incident on a large deviation in either direction.
    """
    MIN_SAMPLES = 5
    OVER_MULTIPLIER = 3.0
    UNDER_FRACTION = 0.20

    db_path = db_path or db_module.DB_PATH
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db_module.apply_connection_pragmas(db)
        async with db.execute(
            """
            SELECT AVG(je.duration_seconds) AS avg_dur, COUNT(*) AS cnt
            FROM job_executions je
            WHERE je.job_id = ?
              AND je.status IN ('success', 'failed')
              AND je.id != ?
              AND je.duration_seconds IS NOT NULL
            """,
            (job_id, execution_id),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None or row["cnt"] < MIN_SAMPLES or row["avg_dur"] is None:
            return

        avg_dur = row["avg_dur"]
        if avg_dur <= 0:
            return

        async with db.execute(
            "SELECT name, notify_channel_ids FROM schedule_jobs WHERE id = ?", (job_id,)
        ) as cursor:
            job_row = await cursor.fetchone()
        if not job_row:
            return
        job_name = job_row["name"]

        ratio = current_duration / avg_dur
        if ratio > OVER_MULTIPLIER:
            anomaly = (
                f"Zombie process detected: job '{job_name}' ran for "
                f"{current_duration:.1f}s (avg: {avg_dur:.1f}s, {ratio:.1f}x over average)"
            )
        elif ratio < UNDER_FRACTION:
            anomaly = (
                f"Suspiciously short run: job '{job_name}' finished in "
                f"{current_duration:.1f}s (avg: {avg_dur:.1f}s, only {ratio * 100:.0f}% of average)"
            )
        else:
            return

        async with db.execute(
            """
            SELECT id FROM incidents
            WHERE source_type = 'schedule' AND source_id = ? AND status = 'open'
              AND title LIKE 'Abnormal duration for job%'
            """,
            (job_id,),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing:
            return

        await db.execute(
            """
            INSERT INTO incidents (title, source_type, source_id, status, severity, description)
            VALUES (?, 'schedule', ?, 'open', 'warning', ?)
            """,
            (f"Abnormal duration for job '{job_name}'", job_id, anomaly),
        )
        await db.commit()

        channel_ids = parse_channel_ids(job_row["notify_channel_ids"])
        if channel_ids:
            await notifier.dispatch(
                db, channel_ids,
                notifier.Alert(
                    title=f"Abnormal duration for job '{job_name}'",
                    body=anomaly,
                    severity="warning",
                    source="script-manager/schedules",
                ),
            )


async def resolve_job_incidents(db, job_id: int):
    """Close open incidents for a job after a successful run."""
    await db.execute(
        """
        UPDATE incidents
        SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE source_type = 'schedule' AND source_id = ? AND status IN ('open', 'acknowledged')
        """,
        (job_id,),
    )


# ── Monitor evaluation ────────────────────────────────────────────────────────

async def evaluate_monitors(db) -> List[int]:
    """
    Flip overdue monitors to 'failing', open an incident and notify.

    Returns the ids of monitors that newly transitioned to failing.
    """
    now = datetime.now(timezone.utc)
    transitioned: List[int] = []

    async with db.execute("SELECT * FROM monitors WHERE status != 'paused'") as cursor:
        monitors = await cursor.fetchall()

    for monitor in monitors:
        if monitor["status"] == "failing":
            continue

        # A monitor that never received its first ping is exactly the case a
        # fail-safe monitor exists to catch (the cron job never ran at all), so
        # the deadline is measured from creation when there is no ping yet.
        reference = parse_sqlite_timestamp(
            monitor["last_ping_at"] or monitor["created_at"]
        )
        if reference is None:
            continue
        never_pinged = monitor["last_ping_at"] is None

        deadline = monitor["expected_interval_seconds"] + monitor["grace_period_seconds"]
        elapsed = (now - reference).total_seconds()
        if elapsed <= deadline:
            continue

        await db.execute(
            "UPDATE monitors SET status = 'failing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (monitor["id"],),
        )
        transitioned.append(monitor["id"])

        title = f"Monitor '{monitor['name']}' is overdue"
        description = (
            f"No ping has ever been received; {int(elapsed)}s since the monitor "
            f"was created (deadline: {deadline}s)"
            if never_pinged else
            f"No ping received for {int(elapsed)}s (deadline: {deadline}s)"
        )

        async with db.execute(
            "SELECT id FROM incidents WHERE source_type='monitor' AND source_id=? AND status='open'",
            (monitor["id"],),
        ) as cursor:
            existing = await cursor.fetchone()
        if not existing:
            await db.execute(
                """
                INSERT INTO incidents (title, source_type, source_id, status, severity, description)
                VALUES (?, 'monitor', ?, 'open', 'critical', ?)
                """,
                (title, monitor["id"], description),
            )

        channel_ids = parse_channel_ids(monitor["notify_channel_ids"])
        if channel_ids:
            await notifier.dispatch(
                db, channel_ids,
                notifier.Alert(
                    title=title, body=description,
                    severity="critical", source="script-manager/monitors",
                ),
            )

    if transitioned:
        await db.commit()
    return transitioned


# ── Loops ─────────────────────────────────────────────────────────────────────

async def _due_jobs(db, now: datetime):
    """Yield jobs that are enabled and due to run."""
    async with db.execute(
        "SELECT * FROM schedule_jobs WHERE enabled = 1"
    ) as cursor:
        return await cursor.fetchall()


async def tick_scheduler(db_path: Optional[str] = None) -> int:
    """
    Run one scheduler pass. Returns the number of jobs started.

    Exposed separately from the loop so it can be tested and triggered on demand.
    """
    db_path = db_path or db_module.DB_PATH
    now = datetime.now(timezone.utc)
    started = 0

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db_module.apply_connection_pragmas(db)

        for job in await _due_jobs(db, now):
            job_id = job["id"]
            next_run = parse_sqlite_timestamp(job["next_run_at"])

            if next_run is None:
                # Newly enabled job, or one created before scheduling existed.
                computed = await compute_next_run(job["cron_expression"], job["timezone"], now)
                await db.execute(
                    "UPDATE schedule_jobs SET next_run_at = ? WHERE id = ?", (computed, job_id)
                )
                continue

            if next_run > now:
                continue

            # Always advance the schedule first so a failure cannot cause a hot loop.
            computed = await compute_next_run(job["cron_expression"], job["timezone"], now)
            await db.execute(
                "UPDATE schedule_jobs SET next_run_at = ? WHERE id = ?", (computed, job_id)
            )
            await db.commit()

            if (now - next_run).total_seconds() > MAX_CATCHUP_SECONDS:
                logger.info(
                    "Skipping job '%s': scheduled run at %s is older than the catch-up window",
                    job["name"], next_run.isoformat(),
                )
                continue

            command = job["command"] or ""
            if not command and job["script_id"]:
                async with db.execute(
                    "SELECT path FROM scripts WHERE id = ?", (job["script_id"],)
                ) as cursor:
                    script_row = await cursor.fetchone()
                if script_row:
                    command = script_row[0]
            if not command:
                logger.warning("Job '%s' has no command and no resolvable script", job["name"])
                continue

            if job["prevent_overlap"]:
                async with db.execute(
                    "SELECT id FROM job_executions WHERE job_id = ? AND status = 'running'",
                    (job_id,),
                ) as cursor:
                    if await cursor.fetchone():
                        logger.info(
                            "Skipping job '%s': a previous run is still in progress", job["name"]
                        )
                        continue

            cursor = await db.execute(
                """
                INSERT INTO job_executions (job_id, started_at, status, triggered_by)
                VALUES (?, ?, 'running', 'scheduler')
                """,
                (job_id, now.isoformat()),
            )
            execution_id = cursor.lastrowid
            await db.commit()

            asyncio.create_task(run_job_execution(
                execution_id=execution_id,
                job_id=job_id,
                command=command,
                timeout=job["timeout_seconds"],
                max_retries=job["max_retries"],
                retry_delay=job["retry_delay_seconds"],
                db_path=db_path,
            ))
            started += 1

        await db.commit()

    return started


async def tick_monitors(db_path: Optional[str] = None) -> int:
    """Run one monitor evaluation pass. Returns the number newly marked failing."""
    db_path = db_path or db_module.DB_PATH
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db_module.apply_connection_pragmas(db)
        return len(await evaluate_monitors(db))


async def reap_stale_executions(db_path: Optional[str] = None) -> int:
    """
    Mark executions that were left 'running' by a backend restart as failed.

    Without this, `prevent_overlap` would refuse to ever run the job again.
    """
    db_path = db_path or db_module.DB_PATH
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db_module.apply_connection_pragmas(db)
        async with db.execute(
            "SELECT id, started_at FROM job_executions WHERE status = 'running'"
        ) as cursor:
            rows = await cursor.fetchall()

        stale = []
        for row in rows:
            started = parse_sqlite_timestamp(row["started_at"])
            if started is None or started < cutoff:
                stale.append(row["id"])

        for execution_id in stale:
            await db.execute(
                """
                UPDATE job_executions
                SET status = 'failed', ended_at = CURRENT_TIMESTAMP,
                    stderr = COALESCE(stderr, '') ||
                             '\nMarked failed: the backend restarted while this run was in progress.'
                WHERE id = ?
                """,
                (execution_id,),
            )
        if stale:
            await db.commit()
        return len(stale)


async def scheduler_loop(stop_event: asyncio.Event, db_path: Optional[str] = None):
    """Main background loop: fires due jobs and evaluates monitors every tick."""
    logger.info("Scheduler started (tick=%ss)", TICK_SECONDS)
    try:
        await reap_stale_executions(db_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not reap stale executions: %s", exc)

    while not stop_event.is_set():
        try:
            started = await tick_scheduler(db_path)
            if started:
                logger.info("Scheduler started %d job(s)", started)
        except Exception as exc:  # noqa: BLE001 - one bad tick must not kill the loop
            logger.exception("Scheduler tick failed: %s", exc)

        try:
            failing = await tick_monitors(db_path)
            if failing:
                logger.warning("%d monitor(s) transitioned to failing", failing)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Monitor evaluation tick failed: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            continue

    logger.info("Scheduler stopped")


class SchedulerHandle:
    """Owns the background task so the app lifespan can start and stop it cleanly."""

    def __init__(self):
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self, db_path: Optional[str] = None):
        if self._task is not None:
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(scheduler_loop(self._stop, db_path))

    async def stop(self):
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        finally:
            self._task = None
