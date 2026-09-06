"""
Notification delivery service.

Turns a configured notification channel into an actual outbound message.
Every sender is best-effort: a failure is reported back to the caller as a
``DeliveryResult`` rather than raised, so one broken channel never stops the
others (or the scheduler / monitor loop that triggered the alert).

Supported channel types and their ``config`` keys:

  slack      webhook_url
  discord    webhook_url
  webhook    url, method (default POST), headers (dict)
  pagerduty  routing_key, (optional) severity
  email      smtp_host, smtp_port, to, from, (optional) smtp_user,
             smtp_pass, use_tls (default true)
  sms        provider ("twilio"), account_sid, auth_token, from, to
"""
from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Outbound requests must never stall a scheduler tick or an API request.
HTTP_TIMEOUT_SECONDS = 10.0
SMTP_TIMEOUT_SECONDS = 15.0

VALID_CHANNEL_TYPES = {"slack", "discord", "email", "webhook", "pagerduty", "sms"}

# Config keys whose values are secrets. They are never returned by the API and
# are preserved (rather than overwritten) when a client submits the placeholder.
SECRET_CONFIG_KEYS = {
    "webhook_url", "url", "auth_token", "account_sid", "routing_key",
    "smtp_pass", "smtp_password", "password", "token", "api_key", "secret",
}

REDACTED = "***"

SEVERITY_COLORS = {
    "critical": "#dc2626",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}


@dataclass
class DeliveryResult:
    """Outcome of a single delivery attempt."""
    channel_id: Optional[int]
    channel_name: str
    channel_type: str
    success: bool
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_type": self.channel_type,
            "success": self.success,
            "detail": self.detail,
        }


@dataclass
class Alert:
    """A message to deliver through one or more channels."""
    title: str
    body: str = ""
    severity: str = "warning"
    source: str = "script-manager"
    links: Dict[str, str] = field(default_factory=dict)

    def as_text(self) -> str:
        parts = [self.title]
        if self.body:
            parts.append(self.body)
        for label, url in self.links.items():
            parts.append(f"{label}: {url}")
        return "\n".join(parts)


def redact_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of `config` with secret values replaced by '***'."""
    if not isinstance(config, dict):
        return {}
    return {
        key: REDACTED if key.lower() in SECRET_CONFIG_KEYS and value not in (None, "") else value
        for key, value in config.items()
    }


def merge_config(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge a client-submitted config over the stored one.

    Because reads are redacted, a client that edits a channel will send back
    ``"***"`` for any secret it did not change. Treat that as "keep the stored
    value" so editing a channel name cannot silently wipe its webhook URL.
    """
    existing = existing if isinstance(existing, dict) else {}
    incoming = incoming if isinstance(incoming, dict) else {}
    merged = dict(incoming)
    for key, value in incoming.items():
        if value == REDACTED and key in existing:
            merged[key] = existing[key]
    return merged


def validate_channel_config(channel_type: str, config: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable problems with the config (empty if valid)."""
    config = config if isinstance(config, dict) else {}
    problems: List[str] = []

    def require(*keys: str):
        for key in keys:
            if not str(config.get(key) or "").strip():
                problems.append(f"'{key}' is required for {channel_type} channels")

    if channel_type in ("slack", "discord"):
        require("webhook_url")
    elif channel_type == "webhook":
        require("url")
        method = str(config.get("method") or "POST").upper()
        if method not in ("POST", "PUT", "PATCH"):
            problems.append("'method' must be POST, PUT or PATCH")
        headers = config.get("headers")
        if headers is not None and not isinstance(headers, dict):
            problems.append("'headers' must be an object")
    elif channel_type == "pagerduty":
        require("routing_key")
    elif channel_type == "email":
        require("smtp_host", "to")
        port = config.get("smtp_port", 587)
        try:
            port = int(port)
            if not 1 <= port <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            problems.append("'smtp_port' must be a port number between 1 and 65535")
    elif channel_type == "sms":
        provider = str(config.get("provider") or "twilio").lower()
        if provider != "twilio":
            problems.append("only the 'twilio' SMS provider is supported")
        require("account_sid", "auth_token", "to")
        if not str(config.get("from") or config.get("from_number") or "").strip():
            problems.append("'from' is required for sms channels")

    return problems


# ── Individual senders ────────────────────────────────────────────────────────

async def _post_json(url: str, payload: Any, headers: Optional[Dict[str, str]] = None,
                     method: str = "POST") -> httpx.Response:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.request(method, url, json=payload, headers=headers or {})
    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code}: {response.text[:200] or 'no response body'}"
        )
    return response


async def _send_slack(config: Dict[str, Any], alert: Alert):
    payload = {
        "text": alert.title,
        "attachments": [{
            "color": SEVERITY_COLORS.get(alert.severity, "#6b7280"),
            "text": alert.body or alert.title,
            "footer": alert.source,
            "fields": [
                {"title": label, "value": url, "short": False}
                for label, url in alert.links.items()
            ],
        }],
    }
    await _post_json(config["webhook_url"], payload)
    return "Delivered to Slack"


async def _send_discord(config: Dict[str, Any], alert: Alert):
    colour = int(SEVERITY_COLORS.get(alert.severity, "#6b7280").lstrip("#"), 16)
    payload = {
        "content": alert.title,
        "embeds": [{
            "title": alert.title,
            "description": alert.body or None,
            "color": colour,
            "footer": {"text": alert.source},
        }],
    }
    await _post_json(config["webhook_url"], payload)
    return "Delivered to Discord"


async def _send_webhook(config: Dict[str, Any], alert: Alert):
    payload = {
        "title": alert.title,
        "body": alert.body,
        "severity": alert.severity,
        "source": alert.source,
        "links": alert.links,
    }
    headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    method = str(config.get("method") or "POST").upper()
    await _post_json(config["url"], payload, headers=headers, method=method)
    return f"Delivered via {method} webhook"


async def _send_pagerduty(config: Dict[str, Any], alert: Alert):
    severity = str(config.get("severity") or alert.severity).lower()
    if severity not in ("critical", "error", "warning", "info"):
        severity = "warning"
    payload = {
        "routing_key": config["routing_key"],
        "event_action": "trigger",
        "payload": {
            "summary": alert.title[:1024],
            "source": alert.source,
            "severity": severity,
            "custom_details": {"body": alert.body, **alert.links},
        },
    }
    await _post_json("https://events.pagerduty.com/v2/enqueue", payload)
    return "Event queued with PagerDuty"


def _send_email_blocking(config: Dict[str, Any], alert: Alert) -> str:
    message = EmailMessage()
    message["Subject"] = f"[{alert.severity.upper()}] {alert.title}"
    message["From"] = config.get("from") or config.get("smtp_user") or "script-manager@localhost"
    recipients = config["to"]
    if isinstance(recipients, (list, tuple)):
        recipients = ", ".join(recipients)
    message["To"] = recipients
    message.set_content(alert.as_text())

    host = config["smtp_host"]
    port = int(config.get("smtp_port") or 587)
    use_tls = config.get("use_tls", True)

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS,
                                  context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        if port != 465 and use_tls:
            server.starttls(context=ssl.create_default_context())
        user = config.get("smtp_user")
        password = config.get("smtp_pass") or config.get("smtp_password")
        if user and password:
            server.login(user, password)
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - closing errors must not mask the send result
            pass
    return f"Email sent to {recipients}"


async def _send_email(config: Dict[str, Any], alert: Alert):
    # smtplib is blocking; keep it off the event loop.
    return await asyncio.to_thread(_send_email_blocking, config, alert)


async def _send_sms(config: Dict[str, Any], alert: Alert):
    account_sid = config["account_sid"]
    auth_token = config["auth_token"]
    from_number = config.get("from") or config.get("from_number")
    to_number = config["to"]
    body = alert.as_text()[:1500]

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            data={"From": from_number, "To": to_number, "Body": body},
            auth=(account_sid, auth_token),
        )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    return f"SMS sent to {to_number}"


SENDERS = {
    "slack": _send_slack,
    "discord": _send_discord,
    "webhook": _send_webhook,
    "pagerduty": _send_pagerduty,
    "email": _send_email,
    "sms": _send_sms,
}


# ── Public API ────────────────────────────────────────────────────────────────

async def send_to_channel(channel: Dict[str, Any], alert: Alert) -> DeliveryResult:
    """Deliver `alert` through a single channel row (dict with name/type/config)."""
    channel_id = channel.get("id")
    name = channel.get("name") or f"channel-{channel_id}"
    channel_type = str(channel.get("type") or "").lower()
    config = channel.get("config") or {}
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            config = {}

    def result(success: bool, detail: str) -> DeliveryResult:
        return DeliveryResult(channel_id, name, channel_type, success, detail)

    if not channel.get("enabled", True):
        return result(False, "Channel is disabled")

    sender = SENDERS.get(channel_type)
    if sender is None:
        return result(False, f"Unsupported channel type '{channel_type}'")

    problems = validate_channel_config(channel_type, config)
    if problems:
        return result(False, "; ".join(problems))

    try:
        detail = await sender(config, alert)
        return result(True, detail or "Delivered")
    except httpx.TimeoutException:
        return result(False, f"Timed out after {HTTP_TIMEOUT_SECONDS:.0f}s")
    except httpx.HTTPError as exc:
        return result(False, f"Network error: {exc}")
    except KeyError as exc:
        return result(False, f"Missing config key: {exc}")
    except Exception as exc:  # noqa: BLE001 - report, never propagate
        logger.warning("Notification delivery failed for channel %s: %s", name, exc)
        return result(False, str(exc))


async def load_channels(db, channel_ids: Optional[Iterable[int]] = None) -> List[Dict[str, Any]]:
    """Load enabled notification channels, optionally restricted to `channel_ids`."""
    ids = [int(cid) for cid in (channel_ids or [])]
    if channel_ids is not None and not ids:
        return []

    if ids:
        placeholders = ",".join("?" * len(ids))
        query = f"SELECT * FROM notification_channels WHERE enabled = 1 AND id IN ({placeholders})"
        params: tuple = tuple(ids)
    else:
        query = "SELECT * FROM notification_channels WHERE enabled = 1"
        params = ()

    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    channels = []
    for row in rows:
        channel = dict(row)
        if isinstance(channel.get("config"), str):
            try:
                channel["config"] = json.loads(channel["config"])
            except (json.JSONDecodeError, TypeError):
                channel["config"] = {}
        channels.append(channel)
    return channels


async def dispatch(db, channel_ids: Optional[Iterable[int]], alert: Alert) -> List[DeliveryResult]:
    """
    Deliver `alert` to the given channels concurrently.

    Passing None for `channel_ids` broadcasts to every enabled channel.
    Never raises: failures come back inside the returned results.
    """
    channels = await load_channels(db, channel_ids)
    if not channels:
        return []
    results = await asyncio.gather(
        *(send_to_channel(channel, alert) for channel in channels),
        return_exceptions=True,
    )
    delivered: List[DeliveryResult] = []
    for channel, outcome in zip(channels, results):
        if isinstance(outcome, BaseException):
            delivered.append(DeliveryResult(
                channel.get("id"), channel.get("name", "?"),
                str(channel.get("type", "?")), False, str(outcome),
            ))
        else:
            delivered.append(outcome)
    return delivered
