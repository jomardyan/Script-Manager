"""
Heartbeat / Fail-Safe Monitor API endpoints

Monitors listen for periodic pings from external jobs (servers, cron scripts, etc.).
If a ping does not arrive within the expected interval + grace period, the monitor
transitions to 'failing' and an incident is created.
"""
import json
import secrets
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, Query

from app.db.database import get_db
from app.models.schemas import (
    MonitorCreate, MonitorResponse, MonitorUpdate,
    IncidentResponse,
)

router = APIRouter()


def _parse_channel_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _monitor_from_row(row) -> dict:
    d = dict(row)
    d["notify_channel_ids"] = _parse_channel_ids(d.get("notify_channel_ids"))
    return d


async def _create_incident(db: aiosqlite.Connection, monitor_id: int, title: str,
                            description: str, severity: str = "warning") -> int:
    """Create an incident for a failing monitor (skip if an open one already exists)."""
    async with db.execute(
        "SELECT id FROM incidents WHERE source_type='monitor' AND source_id=? AND status='open'",
        (monitor_id,),
    ) as cur:
        existing = await cur.fetchone()
    if existing:
        return existing[0]
    cur = await db.execute(
        """
        INSERT INTO incidents (title, source_type, source_id, status, severity, description)
        VALUES (?, 'monitor', ?, 'open', ?, ?)
        """,
        (title, monitor_id, severity, description),
    )
    return cur.lastrowid


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[MonitorResponse])
async def list_monitors(db: aiosqlite.Connection = Depends(get_db)):
    """List all heartbeat monitors with up-to-date status."""
    await _refresh_monitor_statuses(db)
    async with db.execute("SELECT * FROM monitors ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [_monitor_from_row(r) for r in rows]


@router.post("/", response_model=MonitorResponse, status_code=201)
async def create_monitor(
    data: MonitorCreate, db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new heartbeat monitor."""
    ping_key = secrets.token_urlsafe(24)
    channel_ids_json = json.dumps(data.notify_channel_ids)
    try:
        cur = await db.execute(
            """
            INSERT INTO monitors
                (name, description, expected_interval_seconds, grace_period_seconds,
                 ping_key, notify_channel_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data.name, data.description,
                data.expected_interval_seconds, data.grace_period_seconds,
                ping_key, channel_ids_json,
            ),
        )
        monitor_id = cur.lastrowid
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Monitor name already exists")
    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    return _monitor_from_row(row)


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single monitor."""
    await _refresh_single_monitor_status(db, monitor_id)
    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return _monitor_from_row(row)


@router.put("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: int, data: MonitorUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    """Update a monitor's configuration."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")

    fields, params = [], []
    if data.name is not None:
        fields.append("name = ?"); params.append(data.name)
    if data.description is not None:
        fields.append("description = ?"); params.append(data.description)
    if data.expected_interval_seconds is not None:
        fields.append("expected_interval_seconds = ?"); params.append(data.expected_interval_seconds)
    if data.grace_period_seconds is not None:
        fields.append("grace_period_seconds = ?"); params.append(data.grace_period_seconds)
    if data.notify_channel_ids is not None:
        fields.append("notify_channel_ids = ?"); params.append(json.dumps(data.notify_channel_ids))

    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(monitor_id)
        await db.execute(
            f"UPDATE monitors SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()

    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    return _monitor_from_row(row)


@router.delete("/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a monitor and all its ping history."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")
    await db.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
    await db.commit()


# ── Ping endpoint ─────────────────────────────────────────────────────────────

@router.post("/ping/{ping_key}")
async def receive_ping(ping_key: str, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """
    Receive a heartbeat ping.  Call this URL from your cron script to signal
    that it ran successfully.
    """
    async with db.execute(
        "SELECT id, name FROM monitors WHERE ping_key = ?", (ping_key,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown ping key")

    monitor_id, monitor_name = row[0], row[1]
    source_ip = request.client.host if request.client else None

    await db.execute(
        "INSERT INTO monitor_pings (monitor_id, source_ip) VALUES (?, ?)",
        (monitor_id, source_ip),
    )
    await db.execute(
        """
        UPDATE monitors
        SET last_ping_at = CURRENT_TIMESTAMP, status = 'ok', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (monitor_id,),
    )
    # Resolve any open incident for this monitor
    await db.execute(
        """
        UPDATE incidents
        SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE source_type = 'monitor' AND source_id = ? AND status = 'open'
        """,
        (monitor_id,),
    )
    await db.commit()
    return {"message": f"Ping received for monitor '{monitor_name}'"}


# ── Ping history ──────────────────────────────────────────────────────────────

@router.get("/{monitor_id}/pings")
async def get_monitor_pings(
    monitor_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get recent pings for a monitor."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")
    async with db.execute(
        "SELECT * FROM monitor_pings WHERE monitor_id = ? ORDER BY pinged_at DESC LIMIT ?",
        (monitor_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Incidents for a monitor ───────────────────────────────────────────────────

@router.get("/{monitor_id}/incidents", response_model=List[IncidentResponse])
async def get_monitor_incidents(
    monitor_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    """Get all incidents linked to a monitor."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")
    async with db.execute(
        "SELECT * FROM incidents WHERE source_type='monitor' AND source_id=? ORDER BY created_at DESC",
        (monitor_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _refresh_monitor_statuses(db: aiosqlite.Connection):
    """Check all monitors and flip overdue ones to 'failing', creating incidents."""
    async with db.execute("SELECT * FROM monitors WHERE status != 'paused'") as cur:
        monitors = await cur.fetchall()
    for m in monitors:
        await _refresh_single_monitor_status(db, m["id"], m)
    await db.commit()


async def _refresh_single_monitor_status(
    db: aiosqlite.Connection, monitor_id: int, row=None
):
    if row is None:
        async with db.execute(
            "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return

    last_ping = row["last_ping_at"]
    if last_ping is None:
        # Never pinged yet – preserve existing 'new' status without modification
        return

    now = datetime.now(timezone.utc)
    # Parse last_ping (SQLite stores as string without tz)
    if isinstance(last_ping, str):
        try:
            last_ping_dt = datetime.fromisoformat(last_ping.replace("Z", "+00:00"))
        except ValueError:
            return
    else:
        last_ping_dt = last_ping

    if last_ping_dt.tzinfo is None:
        last_ping_dt = last_ping_dt.replace(tzinfo=timezone.utc)

    deadline_seconds = row["expected_interval_seconds"] + row["grace_period_seconds"]
    elapsed = (now - last_ping_dt).total_seconds()

    if elapsed > deadline_seconds and row["status"] not in ("failing", "paused"):
        await db.execute(
            """
            UPDATE monitors SET status = 'failing', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (monitor_id,),
        )
        await _create_incident(
            db,
            monitor_id,
            f"Monitor '{row['name']}' is overdue",
            f"No ping received for {int(elapsed)}s (deadline: {deadline_seconds}s)",
            severity="critical",
        )
