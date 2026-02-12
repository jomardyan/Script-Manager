# Script Manager Architecture

## Overview

Script Manager is a single-host web application for cataloging script files stored on disk. The backend indexes files, stores metadata in SQLite, and exposes a REST API that powers a React-based UI. Optional services (full-text search, watch mode, similarity detection) extend the core indexing workflow without moving files off disk.

## High-Level Components

- **Frontend (React + Vite)**: Single-page UI for browsing scripts, managing metadata, and running searches.
- **Backend (FastAPI)**: REST API for indexing, metadata CRUD, search, and optional services.
- **SQLite Database**: Stores script metadata, tags, status, audit history, and search indexes.
- **File System**: Script content and optional attachments remain on disk and are accessed by the backend.

## Data Flow

1. **Folder roots registered** → backend scanner indexes script metadata (path, hash, size, language).
2. **Metadata stored** → SQLite holds script records, tags, notes, status, and history.
3. **Search & browse** → frontend queries the API for lists, filters, and full-text search results.
4. **Ongoing updates** → watch mode observes file changes and updates metadata automatically.

## Backend Modules

- `app/routes/`: API endpoints for scripts, tags, notes, search, watch mode, FTS, similarity, attachments, and auth.
- `app/services/`: Scanner, watch manager, full-text search, similarity detection, markdown rendering, and auth helpers.
- `app/db/`: Database initialization and connection management.
- `app/models/`: Pydantic request/response schemas.

## Database Overview

- **folder_roots**: Registered directories and scanning configuration.
- **folders**: Folder hierarchy metadata.
- **scripts**: Script metadata and fingerprints.
- **script_notes**: Notes tied to scripts (Markdown supported).
- **tags** / **script_tags**: Tag catalog and assignments.
- **script_fields**: Custom key-value metadata.
- **script_status**: Lifecycle and classification data.
- **scan_events**: Scan history and counters.
- **change_log**: Audit trail for metadata changes.
- **attachments**: Uploaded file metadata.
- **users**, **roles**, **user_roles**: Authentication and authorization data.
- **saved_searches**: Stored search criteria.
- **scripts_fts**: Optional FTS5 index for full-text search.

## Deployment Notes

- The backend runs on FastAPI (default port `8000`) and should have access to the script roots on disk.
- The frontend can be served separately (Vite dev server) or built as static assets and hosted alongside the API.
