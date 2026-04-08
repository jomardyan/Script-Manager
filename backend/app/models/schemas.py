"""
Pydantic models for API request/response
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

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
    last_scan_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class ScriptResponse(BaseModel):
    id: int
    root_id: int
    folder_id: Optional[int]
    path: str
    name: str
    extension: Optional[str]
    language: Optional[str]
    size: Optional[int]
    mtime: Optional[datetime]
    hash: Optional[str]
    line_count: Optional[int]
    missing_flag: bool
    created_at: datetime
    updated_at: datetime
    tags: List[str] = []
    status: Optional[str] = None
    classification: Optional[str] = None
    owner: Optional[str] = None
    environment: Optional[str] = None
    deprecated_date: Optional[datetime] = None
    migration_note: Optional[str] = None
    notes: Optional[str] = None

class ScriptListResponse(BaseModel):
    id: int
    name: str
    path: str
    extension: Optional[str]
    language: Optional[str]
    size: Optional[int]
    mtime: Optional[datetime]
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
    created_at: datetime

class NoteCreate(BaseModel):
    content: str
    is_markdown: bool = False

class NoteResponse(BaseModel):
    id: int
    script_id: int
    content: str
    is_markdown: bool
    created_at: datetime
    updated_at: datetime

class StatusUpdate(BaseModel):
    status: Optional[str] = None
    classification: Optional[str] = None
    owner: Optional[str] = None
    environment: Optional[str] = None
    deprecated_date: Optional[datetime] = None
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
    started_at: datetime
    ended_at: Optional[datetime]

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
    modified_after: Optional[datetime] = None
    modified_before: Optional[datetime] = None
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
    created_at: datetime

class FolderNoteUpdate(BaseModel):
    note: str

class BulkTagRequest(BaseModel):
    script_ids: List[int]
    tag_ids: List[int]

class BulkStatusRequest(BaseModel):
    script_ids: List[int]
    status: Optional[str] = None
    classification: Optional[str] = None
    owner: Optional[str] = None
    environment: Optional[str] = None

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
    created_at: datetime
    updated_at: datetime

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
    created_at: datetime


# ── Heartbeat Monitors ──────────────────────────────────────────────────────

class MonitorCreate(BaseModel):
    name: str
    description: Optional[str] = None
    expected_interval_seconds: int = 300
    grace_period_seconds: int = 60
    notify_channel_ids: List[int] = []

class MonitorResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    expected_interval_seconds: int
    grace_period_seconds: int
    ping_key: str
    last_ping_at: Optional[datetime]
    status: str
    notify_channel_ids: List[int] = []
    created_at: datetime
    updated_at: datetime

class MonitorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    expected_interval_seconds: Optional[int] = None
    grace_period_seconds: Optional[int] = None
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
    max_retries: int = 0
    retry_delay_seconds: int = 60
    prevent_overlap: bool = True
    timeout_seconds: Optional[int] = None
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
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_status: Optional[str]
    created_at: datetime
    updated_at: datetime

class ScheduleJobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    script_id: Optional[int] = None
    command: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[int] = None
    prevent_overlap: Optional[bool] = None
    timeout_seconds: Optional[int] = None
    notify_channel_ids: Optional[List[int]] = None

class JobExecutionResponse(BaseModel):
    id: int
    job_id: int
    started_at: datetime
    ended_at: Optional[datetime]
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
    created_at: datetime
    updated_at: datetime

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
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    acknowledged_by: Optional[str] = None


# ── User management request bodies ──────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None

class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    role_ids: Optional[List[int]] = None
