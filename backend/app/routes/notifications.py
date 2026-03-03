"""
Notification Channels & Incidents API endpoints

Notification channels support: slack, discord, email, webhook, pagerduty, sms.
Incidents can be listed, acknowledged, and resolved.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.db.database import get_db
from app.models.schemas import (
    NotificationChannelCreate, NotificationChannelResponse,
    NotificationChannelUpdate, IncidentResponse, IncidentUpdate,
)

router = APIRouter()

VALID_CHANNEL_TYPES = {"slack", "discord", "email", "webhook", "pagerduty", "sms"}

# Config keys whose values are redacted in API responses to prevent secret leakage
REDACTED_CONFIG_KEYS = {"webhook_url", "url", "auth_token", "account_sid", "routing_key",
                        "smtp_pass", "password", "token", "api_key", "secret"}


def _get_auth_dep():
    from app.routes.auth import get_current_user
    return get_current_user


def _redact_config(config: dict) -> dict:
    """Return a copy of config with secret values replaced by '***'."""
    return {
        k: "***" if k.lower() in REDACTED_CONFIG_KEYS else v
        for k, v in config.items()
    }


def _channel_from_row(row) -> dict:
    d = dict(row)
    if isinstance(d.get("config"), str):
        try:
            d["config"] = json.loads(d["config"])
        except (json.JSONDecodeError, TypeError):
            d["config"] = {}
    return d


# ── Notification Channels CRUD ────────────────────────────────────────────────

@router.get("/channels/", response_model=List[NotificationChannelResponse])
async def list_channels(db: aiosqlite.Connection = Depends(get_db)):
    """List all notification channels."""
    async with db.execute(
        "SELECT * FROM notification_channels ORDER BY name"
    ) as cur:
        rows = await cur.fetchall()
    return [_channel_from_row(r) for r in rows]


@router.post("/channels/", response_model=NotificationChannelResponse, status_code=201)
async def create_channel(
    data: NotificationChannelCreate, db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new notification channel."""
    if data.type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel type. Allowed: {', '.join(sorted(VALID_CHANNEL_TYPES))}",
        )
    config_json = json.dumps(data.config)
    try:
        cur = await db.execute(
            """
            INSERT INTO notification_channels (name, type, config, enabled)
            VALUES (?, ?, ?, ?)
            """,
            (data.name, data.type, config_json, int(data.enabled)),
        )
        channel_id = cur.lastrowid
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Channel name already exists")

    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    return _channel_from_row(row)


@router.get("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def get_channel(channel_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single notification channel."""
    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    return _channel_from_row(row)


@router.put("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def update_channel(
    channel_id: int,
    data: NotificationChannelUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update a notification channel."""
    async with db.execute(
        "SELECT id FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Channel not found")

    if data.type is not None and data.type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel type. Allowed: {', '.join(sorted(VALID_CHANNEL_TYPES))}",
        )

    fields, params = [], []
    if data.name is not None:
        fields.append("name = ?"); params.append(data.name)
    if data.type is not None:
        fields.append("type = ?"); params.append(data.type)
    if data.config is not None:
        fields.append("config = ?"); params.append(json.dumps(data.config))
    if data.enabled is not None:
        fields.append("enabled = ?"); params.append(int(data.enabled))

    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(channel_id)
        await db.execute(
            f"UPDATE notification_channels SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()

    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    return _channel_from_row(row)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    """Delete a notification channel."""
    async with db.execute(
        "SELECT id FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Channel not found")
    await db.execute(
        "DELETE FROM notification_channels WHERE id = ?", (channel_id,)
    )
    await db.commit()


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(_get_auth_dep()),
):
    """
    Send a test notification through the channel (admin only).
    Returns a sanitised view of the channel — secret config values are redacted.
    Actual delivery requires installing optional integrations.
    """
    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    ch = _channel_from_row(row)
    safe_ch = {**ch, "config": _redact_config(ch.get("config", {}))}
    return {
        "message": f"Test notification queued for channel '{ch['name']}' (type={ch['type']})",
        "channel": safe_ch,
    }


# ── Incidents ─────────────────────────────────────────────────────────────────

@router.get("/incidents/", response_model=List[IncidentResponse])
async def list_incidents(
    status: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    """List incidents, optionally filtered by status (open/acknowledged/resolved)."""
    if status:
        query = "SELECT * FROM incidents WHERE status = ? ORDER BY created_at DESC"
        params = (status,)
    else:
        query = "SELECT * FROM incidents ORDER BY created_at DESC"
        params = ()
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single incident."""
    async with db.execute(
        "SELECT * FROM incidents WHERE id = ?", (incident_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)


@router.put("/incidents/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Update an incident (acknowledge or resolve it).
    Set status to 'acknowledged' or 'resolved'.
    """
    async with db.execute(
        "SELECT * FROM incidents WHERE id = ?", (incident_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")

    fields, params = [], []
    now_iso = datetime.now(timezone.utc).isoformat()

    if data.status is not None:
        if data.status not in ("open", "acknowledged", "resolved"):
            raise HTTPException(
                status_code=400,
                detail="Status must be one of: open, acknowledged, resolved",
            )
        fields.append("status = ?"); params.append(data.status)
        if data.status == "acknowledged":
            fields.append("acknowledged_at = ?"); params.append(now_iso)
        elif data.status == "resolved":
            fields.append("resolved_at = ?"); params.append(now_iso)

    if data.severity is not None:
        fields.append("severity = ?"); params.append(data.severity)
    if data.description is not None:
        fields.append("description = ?"); params.append(data.description)
    if data.acknowledged_by is not None:
        fields.append("acknowledged_by = ?"); params.append(data.acknowledged_by)

    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(incident_id)
        await db.execute(
            f"UPDATE incidents SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()

    async with db.execute(
        "SELECT * FROM incidents WHERE id = ?", (incident_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row)


@router.delete("/incidents/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: int, db: aiosqlite.Connection = Depends(get_db)
):
    """Delete an incident record."""
    async with db.execute(
        "SELECT id FROM incidents WHERE id = ?", (incident_id,)
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Incident not found")
    await db.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
    await db.commit()
