"""
Notification Channels & Incidents API endpoints

Notification channels support: slack, discord, email, webhook, pagerduty, sms.
Secrets inside a channel's config are never returned by the API; clients see
"***" and may send it back unchanged to keep the stored value.

Incidents can be listed, acknowledged, resolved and deleted.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.database import get_db
from app.models.schemas import (
    NotificationChannelCreate, NotificationChannelResponse,
    NotificationChannelUpdate, IncidentResponse, IncidentUpdate,
)
from app.routes.deps import actor_name, get_optional_user, require_permission
from app.services import notifier

router = APIRouter()

VALID_CHANNEL_TYPES = notifier.VALID_CHANNEL_TYPES
VALID_INCIDENT_STATUSES = ("open", "acknowledged", "resolved")
VALID_SEVERITIES = ("info", "warning", "critical")

read_access = Depends(require_permission("notifications.read"))
write_access = Depends(require_permission("notifications.update"))
incident_read = Depends(require_permission("incidents.read"))
incident_write = Depends(require_permission("incidents.update"))


def _channel_from_row(row, redact: bool = True) -> dict:
    """Convert a channel row to a dict, redacting secret config values by default."""
    d = dict(row)
    config = d.get("config")
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            config = {}
    if not isinstance(config, dict):
        config = {}
    d["config"] = notifier.redact_config(config) if redact else config
    d["enabled"] = bool(d.get("enabled"))
    return d


def _validate_type_and_config(channel_type: str, config: dict):
    if channel_type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel type. Allowed: {', '.join(sorted(VALID_CHANNEL_TYPES))}",
        )
    problems = notifier.validate_channel_config(channel_type, config)
    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems))


async def _load_raw_config(db: aiosqlite.Connection, channel_id: int) -> dict:
    async with db.execute(
        "SELECT config FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


# ── Notification Channels CRUD ────────────────────────────────────────────────

@router.get("/channels/", response_model=List[NotificationChannelResponse],
            dependencies=[read_access])
async def list_channels(db: aiosqlite.Connection = Depends(get_db)):
    """List all notification channels (secrets redacted)."""
    async with db.execute(
        "SELECT * FROM notification_channels ORDER BY name"
    ) as cur:
        rows = await cur.fetchall()
    return [_channel_from_row(r) for r in rows]


@router.get("/channels/types", dependencies=[read_access])
async def list_channel_types():
    """
    Describe the supported channel types and the config keys each expects,
    so the UI can render a real form instead of a raw JSON textarea.
    """
    return {
        "types": [
            {
                "type": "slack",
                "label": "Slack",
                "fields": [
                    {"key": "webhook_url", "label": "Incoming webhook URL",
                     "required": True, "secret": True,
                     "placeholder": "https://hooks.slack.com/services/..."},
                ],
            },
            {
                "type": "discord",
                "label": "Discord",
                "fields": [
                    {"key": "webhook_url", "label": "Webhook URL",
                     "required": True, "secret": True,
                     "placeholder": "https://discord.com/api/webhooks/..."},
                ],
            },
            {
                "type": "webhook",
                "label": "Generic webhook",
                "fields": [
                    {"key": "url", "label": "Endpoint URL", "required": True, "secret": True,
                     "placeholder": "https://example.com/hooks/alerts"},
                    {"key": "method", "label": "HTTP method", "required": False,
                     "placeholder": "POST"},
                ],
            },
            {
                "type": "pagerduty",
                "label": "PagerDuty",
                "fields": [
                    {"key": "routing_key", "label": "Events API routing key",
                     "required": True, "secret": True},
                ],
            },
            {
                "type": "email",
                "label": "Email (SMTP)",
                "fields": [
                    {"key": "smtp_host", "label": "SMTP host", "required": True,
                     "placeholder": "smtp.example.com"},
                    {"key": "smtp_port", "label": "SMTP port", "required": False,
                     "placeholder": "587"},
                    {"key": "to", "label": "Recipient", "required": True,
                     "placeholder": "ops@example.com"},
                    {"key": "from", "label": "Sender", "required": False,
                     "placeholder": "alerts@example.com"},
                    {"key": "smtp_user", "label": "SMTP username", "required": False},
                    {"key": "smtp_pass", "label": "SMTP password",
                     "required": False, "secret": True},
                ],
            },
            {
                "type": "sms",
                "label": "SMS (Twilio)",
                "fields": [
                    {"key": "account_sid", "label": "Account SID",
                     "required": True, "secret": True},
                    {"key": "auth_token", "label": "Auth token",
                     "required": True, "secret": True},
                    {"key": "from", "label": "From number", "required": True,
                     "placeholder": "+15550000000"},
                    {"key": "to", "label": "To number", "required": True,
                     "placeholder": "+15551234567"},
                ],
            },
        ]
    }


@router.post("/channels/", response_model=NotificationChannelResponse, status_code=201,
             dependencies=[Depends(require_permission("notifications.create"))])
async def create_channel(
    data: NotificationChannelCreate, db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new notification channel."""
    _validate_type_and_config(data.type, data.config)
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


@router.get("/channels/{channel_id}", response_model=NotificationChannelResponse,
            dependencies=[read_access])
async def get_channel(channel_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single notification channel (secrets redacted)."""
    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    return _channel_from_row(row)


@router.put("/channels/{channel_id}", response_model=NotificationChannelResponse,
            dependencies=[write_access])
async def update_channel(
    channel_id: int,
    data: NotificationChannelUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update a notification channel. Secrets left as '***' keep their stored value."""
    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        existing = await cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel_type = data.type if data.type is not None else existing["type"]
    stored_config = await _load_raw_config(db, channel_id)
    new_config = (
        notifier.merge_config(stored_config, data.config)
        if data.config is not None else stored_config
    )
    _validate_type_and_config(channel_type, new_config)

    fields, params = [], []
    if data.name is not None:
        fields.append("name = ?"); params.append(data.name)
    if data.type is not None:
        fields.append("type = ?"); params.append(data.type)
    if data.config is not None:
        fields.append("config = ?"); params.append(json.dumps(new_config))
    if data.enabled is not None:
        fields.append("enabled = ?"); params.append(int(data.enabled))

    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(channel_id)
        try:
            await db.execute(
                f"UPDATE notification_channels SET {', '.join(fields)} WHERE id = ?", params
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=400, detail="Channel name already exists")

    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    return _channel_from_row(row)


@router.delete("/channels/{channel_id}", status_code=204,
               dependencies=[Depends(require_permission("notifications.delete"))])
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


@router.post("/channels/{channel_id}/test", dependencies=[write_access])
async def test_channel(
    channel_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: Optional[dict] = Depends(get_optional_user),
):
    """
    Send a real test notification through the channel and report the outcome.

    Delivery failures come back as ``success: false`` with the provider's error
    rather than as an HTTP error, so the UI can show exactly what went wrong.
    """
    async with db.execute(
        "SELECT * FROM notification_channels WHERE id = ?", (channel_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel = _channel_from_row(row, redact=False)
    who = actor_name(current_user) or "an operator"
    result = await notifier.send_to_channel(
        channel,
        notifier.Alert(
            title="Script Manager test notification",
            body=f"This is a test message sent by {who}. "
                 f"If you can read it, the '{channel['name']}' channel is working.",
            severity="info",
            source="script-manager",
        ),
    )

    return {
        "success": result.success,
        "message": result.detail,
        "channel": {
            "id": channel["id"],
            "name": channel["name"],
            "type": channel["type"],
            "enabled": channel["enabled"],
            "config": notifier.redact_config(channel["config"]),
        },
    }


# ── Incidents ─────────────────────────────────────────────────────────────────

@router.get("/incidents/", response_model=List[IncidentResponse],
            dependencies=[incident_read])
async def list_incidents(
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List incidents, optionally filtered by status and source type."""
    if status and status not in VALID_INCIDENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status must be one of: {', '.join(VALID_INCIDENT_STATUSES)}",
        )

    conditions, params = [], []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    async with db.execute(
        f"SELECT * FROM incidents {where} ORDER BY created_at DESC, id DESC LIMIT ?",
        tuple(params),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/incidents/stats", dependencies=[incident_read])
async def incident_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Counts by status and severity, for the dashboard."""
    async with db.execute(
        "SELECT status, COUNT(*) FROM incidents GROUP BY status"
    ) as cur:
        by_status = {row[0]: row[1] for row in await cur.fetchall()}
    async with db.execute(
        "SELECT severity, COUNT(*) FROM incidents WHERE status != 'resolved' GROUP BY severity"
    ) as cur:
        unresolved_by_severity = {row[0]: row[1] for row in await cur.fetchall()}
    return {
        "by_status": by_status,
        "unresolved_by_severity": unresolved_by_severity,
        "open": by_status.get("open", 0),
        "acknowledged": by_status.get("acknowledged", 0),
        "resolved": by_status.get("resolved", 0),
    }


@router.get("/incidents/{incident_id}", response_model=IncidentResponse,
            dependencies=[incident_read])
async def get_incident(incident_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single incident."""
    async with db.execute(
        "SELECT * FROM incidents WHERE id = ?", (incident_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)


@router.put("/incidents/{incident_id}", response_model=IncidentResponse,
            dependencies=[incident_write])
async def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: Optional[dict] = Depends(get_optional_user),
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
        if data.status not in VALID_INCIDENT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Status must be one of: {', '.join(VALID_INCIDENT_STATUSES)}",
            )
        fields.append("status = ?"); params.append(data.status)
        if data.status == "acknowledged":
            fields.append("acknowledged_at = ?"); params.append(now_iso)
            # Record who acknowledged it unless the caller named someone else.
            if data.acknowledged_by is None and current_user:
                fields.append("acknowledged_by = ?")
                params.append(current_user["username"])
        elif data.status == "resolved":
            fields.append("resolved_at = ?"); params.append(now_iso)

    if data.severity is not None:
        if data.severity not in VALID_SEVERITIES:
            raise HTTPException(
                status_code=400,
                detail=f"Severity must be one of: {', '.join(VALID_SEVERITIES)}",
            )
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


@router.delete("/incidents/{incident_id}", status_code=204, dependencies=[incident_write])
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
