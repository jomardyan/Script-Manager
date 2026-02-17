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
