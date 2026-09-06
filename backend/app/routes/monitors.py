"""
Heartbeat / Fail-Safe Monitor API endpoints

Monitors listen for periodic pings from external jobs (servers, cron scripts, etc.).
If a ping does not arrive within the expected interval + grace period, the monitor
transitions to 'failing', an incident is created and the configured notification
channels are alerted.

Overdue detection runs on a timer in app.services.scheduler, so alerts fire even
when nobody has the UI open. Listing monitors also evaluates them so the page is
never stale.
"""
import json
import secrets
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, Query

from app.db.database import get_db
from app.models.schemas import (
    MonitorCreate, MonitorResponse, MonitorUpdate,
    IncidentResponse,
)
from app.routes.deps import require_permission
from app.services import notifier
from app.services.scheduler import evaluate_monitors, parse_channel_ids

router = APIRouter()

read_access = Depends(require_permission("monitors.read"))
write_access = Depends(require_permission("monitors.update"))

MIN_INTERVAL_SECONDS = 10
MAX_INTERVAL_SECONDS = 60 * 60 * 24 * 31  # a month


def _parse_channel_ids(raw: Optional[str]) -> List[int]:
    return parse_channel_ids(raw)


def _monitor_from_row(row) -> dict:
    d = dict(row)
    d["notify_channel_ids"] = _parse_channel_ids(d.get("notify_channel_ids"))
    return d


def _validate_intervals(expected: Optional[int], grace: Optional[int]):
    if expected is not None and not (MIN_INTERVAL_SECONDS <= expected <= MAX_INTERVAL_SECONDS):
        raise HTTPException(
            status_code=400,
            detail=f"expected_interval_seconds must be between {MIN_INTERVAL_SECONDS} "
                   f"and {MAX_INTERVAL_SECONDS}",
        )
    if grace is not None and not (0 <= grace <= MAX_INTERVAL_SECONDS):
        raise HTTPException(
            status_code=400,
            detail=f"grace_period_seconds must be between 0 and {MAX_INTERVAL_SECONDS}",
        )


async def _verify_channels(db: aiosqlite.Connection, channel_ids: List[int]):
    """Reject references to notification channels that do not exist."""
    if not channel_ids:
        return
    placeholders = ",".join("?" * len(channel_ids))
    async with db.execute(
        f"SELECT id FROM notification_channels WHERE id IN ({placeholders})",
        tuple(channel_ids),
    ) as cur:
        found = {row[0] for row in await cur.fetchall()}
    missing = sorted(set(channel_ids) - found)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown notification channel id(s): {', '.join(str(m) for m in missing)}",
        )


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[MonitorResponse], dependencies=[read_access])
async def list_monitors(db: aiosqlite.Connection = Depends(get_db)):
    """List all heartbeat monitors with up-to-date status."""
    await evaluate_monitors(db)
    async with db.execute("SELECT * FROM monitors ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [_monitor_from_row(r) for r in rows]


@router.post("/", response_model=MonitorResponse, status_code=201,
             dependencies=[Depends(require_permission("monitors.create"))])
async def create_monitor(
    data: MonitorCreate, db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new heartbeat monitor."""
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Monitor name cannot be empty")
    _validate_intervals(data.expected_interval_seconds, data.grace_period_seconds)
    await _verify_channels(db, data.notify_channel_ids)

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
                data.name.strip(), data.description,
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


@router.get("/{monitor_id}", response_model=MonitorResponse, dependencies=[read_access])
async def get_monitor(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single monitor."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")
    await evaluate_monitors(db)
    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    return _monitor_from_row(row)


@router.put("/{monitor_id}", response_model=MonitorResponse, dependencies=[write_access])
async def update_monitor(
    monitor_id: int, data: MonitorUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    """Update a monitor's configuration."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")

    _validate_intervals(data.expected_interval_seconds, data.grace_period_seconds)
    if data.notify_channel_ids is not None:
        await _verify_channels(db, data.notify_channel_ids)

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
        try:
            await db.execute(
                f"UPDATE monitors SET {', '.join(fields)} WHERE id = ?", params
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=400, detail="Monitor name already exists")

    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    return _monitor_from_row(row)


@router.delete("/{monitor_id}", status_code=204,
               dependencies=[Depends(require_permission("monitors.delete"))])
async def delete_monitor(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a monitor and all its ping history."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")
    await db.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
    # Incidents are not FK-linked to monitors (source_id is a loose reference),
    # so clean them up explicitly instead of leaving dangling alerts behind.
    await db.execute(
        "DELETE FROM incidents WHERE source_type = 'monitor' AND source_id = ?", (monitor_id,)
    )
    await db.commit()


@router.post("/{monitor_id}/pause", response_model=MonitorResponse, dependencies=[write_access])
async def pause_monitor(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Pause a monitor (stops overdue detection and alerting)."""
    async with db.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Monitor not found")
    await db.execute(
        "UPDATE monitors SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (monitor_id,),
    )
    await db.commit()
    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    return _monitor_from_row(row)


@router.post("/{monitor_id}/resume", response_model=MonitorResponse, dependencies=[write_access])
async def resume_monitor(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Resume a paused monitor."""
    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Monitor not found")
    if row["status"] != "paused":
        raise HTTPException(status_code=400, detail="Monitor is not paused")
    # Restore to 'new' if never pinged, else 'ok'; the evaluator immediately
    # re-flags it as failing if the last ping is already outside the deadline.
    new_status = "new" if row["last_ping_at"] is None else "ok"
    await db.execute(
        "UPDATE monitors SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_status, monitor_id),
    )
    await db.commit()
    await evaluate_monitors(db)
    async with db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        row = await cur.fetchone()
    return _monitor_from_row(row)


# ── Ping endpoint ─────────────────────────────────────────────────────────────

@router.post("/ping/{ping_key}")
async def receive_ping(ping_key: str, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """
    Receive a heartbeat ping. Call this URL from your cron script to signal
    that it ran successfully.

    Deliberately unauthenticated: the 192-bit random ping key is the credential,
    so a cron job needs nothing but the URL.
    """
    async with db.execute(
        "SELECT id, name, notify_channel_ids FROM monitors WHERE ping_key = ?", (ping_key,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown ping key")

    monitor_id, monitor_name = row[0], row[1]
    channel_ids = _parse_channel_ids(row[2])
    source_ip = request.client.host if request.client else None

    async with db.execute("SELECT status FROM monitors WHERE id = ?", (monitor_id,)) as cur:
        previous_status = (await cur.fetchone())[0]

    await db.execute(
        "INSERT INTO monitor_pings (monitor_id, source_ip) VALUES (?, ?)",
        (monitor_id, source_ip),
    )
    # A ping from a paused monitor should not silently un-pause it.
    new_status = "paused" if previous_status == "paused" else "ok"
    await db.execute(
        """
        UPDATE monitors
        SET last_ping_at = CURRENT_TIMESTAMP, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_status, monitor_id),
    )
    # Resolve any open incident for this monitor
    await db.execute(
        """
        UPDATE incidents
        SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE source_type = 'monitor' AND source_id = ? AND status IN ('open', 'acknowledged')
        """,
        (monitor_id,),
    )
    await db.commit()

    if previous_status == "failing" and channel_ids:
        await notifier.dispatch(
            db, channel_ids,
            notifier.Alert(
                title=f"Monitor '{monitor_name}' recovered",
                body="A heartbeat was received; the monitor is reporting again.",
                severity="info",
                source="script-manager/monitors",
            ),
        )

    return {
        "message": f"Ping received for monitor '{monitor_name}'",
        "monitor_id": monitor_id,
        "status": new_status,
        "recovered": previous_status == "failing",
    }


# ── Ping history ──────────────────────────────────────────────────────────────

@router.get("/{monitor_id}/ping-url", dependencies=[read_access])
async def get_monitor_ping_url(monitor_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """
    Reveal a monitor's ping key.

    Kept on its own endpoint so the key is fetched deliberately rather than
    being handed out in every listing.
    """
    async with db.execute(
        "SELECT name, ping_key FROM monitors WHERE id = ?", (monitor_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return {
        "monitor_id": monitor_id,
        "name": row["name"],
        "ping_key": row["ping_key"],
        "ping_path": f"/api/monitors/ping/{row['ping_key']}",
    }


@router.get("/{monitor_id}/pings", dependencies=[read_access])
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
        "SELECT * FROM monitor_pings WHERE monitor_id = ? ORDER BY pinged_at DESC, id DESC LIMIT ?",
        (monitor_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Incidents for a monitor ───────────────────────────────────────────────────

@router.get("/{monitor_id}/incidents", response_model=List[IncidentResponse],
            dependencies=[read_access])
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
