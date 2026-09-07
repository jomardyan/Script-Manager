"""
Pydantic models for API request/response
"""
from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _as_utc(value: datetime) -> datetime:
    """
    Treat a naive timestamp as UTC and always serialize with an offset.

    SQLite's CURRENT_TIMESTAMP writes naive UTC strings. Serialized without an
    offset, `new Date(value)` in the browser parses them as local time, so
    every timestamp in the UI was shifted by the viewer's UTC offset.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

class FolderRootCreate(BaseModel):
    path: str
    name: str
    recursive: bool = True
    include_patterns: Optional[str] = None
    exclude_patterns: Optional[str] = None
    follow_symlinks: bool = False
    max_file_size: int = 10485760  # 10MB
    enable_content_indexing: bool = False
    enable_watch_mode: bool = False

class FolderRootResponse(BaseModel):
    id: int
    path: str
    name: str
    recursive: bool
    include_patterns: Optional[str]
    exclude_patterns: Optional[str]
    follow_symlinks: bool
    max_file_size: int
    enable_content_indexing: bool
    enable_watch_mode: bool
    last_scan_time: Optional[UTCDateTime]
    created_at: UTCDateTime
    updated_at: UTCDateTime

class FolderRootUpdate(BaseModel):
    """Partial update for a folder root. The path is immutable: changing it
    would orphan every script already indexed under the old location."""
    name: Optional[str] = None
    recursive: Optional[bool] = None
    include_patterns: Optional[str] = None
    exclude_patterns: Optional[str] = None
    follow_symlinks: Optional[bool] = None
    max_file_size: Optional[int] = None
    enable_content_indexing: Optional[bool] = None
    enable_watch_mode: Optional[bool] = None

class ScriptResponse(BaseModel):
    id: int
    root_id: int
    folder_id: Optional[int]
    path: str
    name: str
    extension: Optional[str]
    language: Optional[str]
    size: Optional[int]
    mtime: Optional[UTCDateTime]
    hash: Optional[str]
    line_count: Optional[int]
    missing_flag: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime
    tags: List[str] = []
    status: Optional[str] = None
    classification: Optional[str] = None
    owner: Optional[str] = None
    environment: Optional[str] = None
    deprecated_date: Optional[UTCDateTime] = None
    migration_note: Optional[str] = None
    notes: Optional[str] = None

class ScriptListResponse(BaseModel):
    id: int
    name: str
    path: str
    extension: Optional[str]
    language: Optional[str]
    size: Optional[int]
    mtime: Optional[UTCDateTime]
    status: Optional[str]
    tags: List[str] = []

class TagCreate(BaseModel):
    name: str
    group_name: Optional[str] = None
    color: Optional[str] = None

class TagResponse(BaseModel):
    id: int
    name: str
    group_name: Optional[str]
    color: Optional[str]
    created_at: UTCDateTime

class NoteCreate(BaseModel):
    content: str
    is_markdown: bool = False

class NoteResponse(BaseModel):
    id: int
    script_id: int
    content: str
    is_markdown: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime

# The lifecycle states the UI offers and the docs describe. Typing the field
# means an unknown value is rejected with a 422 instead of being stored and
# then never matching any filter.
ScriptStatus = Literal["active", "draft", "deprecated", "archived"]


class StatusUpdate(BaseModel):
    status: Optional[ScriptStatus] = None
    classification: Optional[str] = None
    owner: Optional[str] = None
    environment: Optional[str] = None
    deprecated_date: Optional[UTCDateTime] = None
    migration_note: Optional[str] = None

class ScanRequest(BaseModel):
    full_scan: bool = False

class ScanResponse(BaseModel):
    scan_id: int
    status: str
    new_count: int
    updated_count: int
    deleted_count: int
    error_count: int
    started_at: UTCDateTime
    ended_at: Optional[UTCDateTime]

class SearchRequest(BaseModel):
    query: Optional[str] = None
    languages: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[List[str]] = None
    root_ids: Optional[List[int]] = None
    owner: Optional[str] = None
    environment: Optional[str] = None
    classification: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    modified_after: Optional[UTCDateTime] = None
    modified_before: Optional[UTCDateTime] = None
    sort_by: str = "name"
    sort_order: str = "asc"
    page: int = 1
    page_size: int = 50

class PaginatedResponse(BaseModel):
    items: List[ScriptListResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class FolderResponse(BaseModel):
    id: int
    root_id: int
    path: str
    parent_id: Optional[int]
    note: Optional[str]
    created_at: UTCDateTime

class FolderNoteUpdate(BaseModel):
    note: str

class BulkTagRequest(BaseModel):
    script_ids: List[int]
    tag_ids: List[int]

class BulkStatusRequest(BaseModel):
    script_ids: List[int]
    status: Optional[ScriptStatus] = None
    classification: Optional[str] = None
    owner: Optional[str] = None
    environment: Optional[str] = None

class ExportRequest(BaseModel):
    """Body for POST /api/scripts/export. Omit script_ids to export everything."""
    script_ids: Optional[List[int]] = None


class SavedSearchCreate(BaseModel):
    name: str
    description: Optional[str] = None
    query_params: dict
    is_pinned: bool = False

class SavedSearchResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    query_params: dict
    is_pinned: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime

class FTSSearchRequest(BaseModel):
    query: str
    search_content: bool = True
    search_notes: bool = True
    page: int = 1
    page_size: int = 50

class AttachmentResponse(BaseModel):
    id: int
    script_id: Optional[int]
    note_id: Optional[int]
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: Optional[str]
    created_at: UTCDateTime


# ── Heartbeat Monitors ──────────────────────────────────────────────────────

class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    expected_interval_seconds: int = Field(default=300, ge=10, le=2678400)
    grace_period_seconds: int = Field(default=60, ge=0, le=2678400)
    notify_channel_ids: List[int] = []

class MonitorResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    expected_interval_seconds: int
    grace_period_seconds: int
    # Omitted from list and detail responses: the key is the credential that
    # lets anything forge a heartbeat. Fetch it deliberately from
    # GET /api/monitors/{id}/ping-url instead.
    ping_key: Optional[str] = None
    last_ping_at: Optional[UTCDateTime]
    status: str
    notify_channel_ids: List[int] = []
    created_at: UTCDateTime
    updated_at: UTCDateTime

class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    expected_interval_seconds: Optional[int] = Field(default=None, ge=10, le=2678400)
    grace_period_seconds: Optional[int] = Field(default=None, ge=0, le=2678400)
    notify_channel_ids: Optional[List[int]] = None


# ── Schedule Jobs ────────────────────────────────────────────────────────────

class ScheduleJobCreate(BaseModel):
    name: str
    description: Optional[str] = None
    script_id: Optional[int] = None
    command: Optional[str] = None
    cron_expression: str
    timezone: str = "UTC"
    enabled: bool = True
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_delay_seconds: int = Field(default=60, ge=1, le=86400)
    prevent_overlap: bool = True
    # ge=1 so timeout_seconds=0 cannot silently mean "no timeout".
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    notify_channel_ids: List[int] = []

class ScheduleJobResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    script_id: Optional[int]
    command: Optional[str]
    cron_expression: str
    timezone: str
    enabled: bool
    max_retries: int
    retry_delay_seconds: int
    prevent_overlap: bool
    timeout_seconds: Optional[int]
    notify_channel_ids: List[int] = []
    last_run_at: Optional[UTCDateTime]
    next_run_at: Optional[UTCDateTime]
    last_status: Optional[str]
    created_at: UTCDateTime
    updated_at: UTCDateTime

class ScheduleJobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    script_id: Optional[int] = None
    command: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    retry_delay_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    prevent_overlap: Optional[bool] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    notify_channel_ids: Optional[List[int]] = None

class JobExecutionResponse(BaseModel):
    id: int
    job_id: int
    started_at: UTCDateTime
    ended_at: Optional[UTCDateTime]
    status: str
    exit_code: Optional[int]
    stdout: Optional[str]
    stderr: Optional[str]
    duration_seconds: Optional[float]
    retry_attempt: int
    triggered_by: str


# ── Notification Channels ────────────────────────────────────────────────────

class NotificationChannelCreate(BaseModel):
    name: str
    type: str  # slack | discord | email | webhook | pagerduty | sms
    config: dict = {}
    enabled: bool = True

class NotificationChannelResponse(BaseModel):
    id: int
    name: str
    type: str
    config: dict
    enabled: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime

class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


# ── Incidents ────────────────────────────────────────────────────────────────

class IncidentResponse(BaseModel):
    id: int
    title: str
    source_type: str
    source_id: Optional[int]
    status: str
    severity: str
    description: Optional[str]
    acknowledged_at: Optional[UTCDateTime]
    acknowledged_by: Optional[str]
    resolved_at: Optional[UTCDateTime]
    created_at: UTCDateTime
    updated_at: UTCDateTime

class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    acknowledged_by: Optional[str] = None


# ── User management request bodies ──────────────────────────────────────────

class UserRegister(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: Optional[str] = Field(default=None, max_length=200)
    # Honoured only for requests made by an administrator.
    role_ids: Optional[List[int]] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, max_length=200)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role_ids: Optional[List[int]] = None
    # Admin-initiated password reset.
    password: Optional[str] = Field(default=None, min_length=8, max_length=256)

class PasswordChange(BaseModel):
    """Body for PUT /api/auth/change-password.

    Credentials belong in the body: as query parameters they end up in access
    logs, browser history and proxy caches.
    """
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)
