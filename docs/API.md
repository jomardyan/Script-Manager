# Script Manager API Documentation

## Base URL

```
http://localhost:8000/api
```

The bundled frontend container proxies `/api` to the backend, so a browser
client can use same-origin relative URLs.

## Authorization

Every endpoint requires a bearer token and the permission named beside it,
except:

- `/api/setup/*` — the installation wizard, which runs before any account exists
- `POST /api/auth/login` and `GET /api/auth/config`
- `GET /health`
- `POST /api/monitors/ping/{ping_key}` — the random ping key is the credential

Send the token as `Authorization: Bearer <token>`. A request without one gets
`401`; one whose account lacks the permission gets `403` naming the permission
required. Set `REQUIRE_AUTH=false` to disable enforcement entirely for a local
single-user setup.

Permissions are `<resource>.<action>`; `<resource>.*` and `superuser` are
wildcards. See the Authentication & RBAC section of the README for the roles.

## Endpoints

### Health Check

**GET /health** - Returns API health status

### Authentication

- **POST /api/auth/login** - Log in (form-encoded) and receive a JWT access token
- **GET /api/auth/me** - Current user, including the flattened permission set
- **GET /api/auth/config** - Public: whether auth is enforced and self-registration is on
- **POST /api/auth/register** - Create a user. Administrators always may; anonymous
  callers only when `ALLOW_SELF_REGISTRATION=true`
- **PUT /api/auth/change-password** - Change the current user's password.
  Takes a JSON body `{old_password, new_password}`; the credentials are not
  accepted as query parameters
- **GET /api/auth/users** - List users (admin)
- **GET /api/auth/users/{id}** - Read a user (admin, or yourself)
- **PUT /api/auth/users/{id}** - Update profile, roles, active state or password (admin)
- **DELETE /api/auth/users/{id}** - Delete a user (admin)
- **GET /api/auth/roles** - List roles and their permissions (admin)

The last remaining administrator cannot be deleted, deactivated or demoted.

### Folder Roots

- **GET /api/folder-roots/** - List all folder roots
- **POST /api/folder-roots/** - Create a new folder root (with enable_content_indexing, enable_watch_mode)
- **GET /api/folder-roots/{id}** - Get a specific folder root
- **DELETE /api/folder-roots/{id}** - Delete a folder root
- **PUT /api/folder-roots/{id}** - Update a root's settings, including
  `enable_content_indexing` and `enable_watch_mode`. The path is immutable
- **GET /api/folder-roots/stats** - Per-root script counts and last scan outcome
- **POST /api/folder-roots/{id}/scan** - Start a scan (returns `202` with a `scan_id`)
- **GET /api/folder-roots/{id}/scan/{scan_id}** - Poll a scan's progress
- **GET /api/folder-roots/{id}/scans** - Recent scan history

### Scripts

- **GET /api/scripts/** - List scripts with pagination and filters
- **GET /api/scripts/{id}** - Get detailed script information
- **GET /api/scripts/{id}/content** - Get script file content (NEW)
- **GET /api/scripts/{id}/history** - Get change history for a script (NEW)
- **PUT /api/scripts/{id}/status** - Update script status
- **POST /api/scripts/{id}/tags/{tag_id}** - Add a tag to a script
- **DELETE /api/scripts/{id}/tags/{tag_id}** - Remove a tag from a script
- **GET /api/scripts/duplicates/list** - Find duplicate scripts
- **POST /api/scripts/bulk/tags** - Add tags to multiple scripts (NEW)
- **POST /api/scripts/bulk/status** - Update status for multiple scripts (NEW)
- **POST /api/scripts/export** - Export script metadata as JSON (NEW)
- **POST /api/scripts/import** - Import script metadata (NEW)

### Custom Fields

- **GET /api/scripts/{id}/fields** - Get all custom fields for a script (NEW)
- **PUT /api/scripts/{id}/fields/{key}** - Set a custom field value (NEW)
- **DELETE /api/scripts/{id}/fields/{key}** - Delete a custom field (NEW)

### Tags

- **GET /api/tags/** - List all tags
- **POST /api/tags/** - Create a new tag
- **GET /api/tags/{id}** - Get a specific tag
- **DELETE /api/tags/{id}** - Delete a tag
- **GET /api/tags/{id}/scripts** - Get scripts with a specific tag

### Notes

- **GET /api/notes/script/{script_id}** - Get notes for a script
- **POST /api/notes/script/{script_id}** - Create a note (with is_markdown support)
- **PUT /api/notes/{note_id}** - Update a note
- **DELETE /api/notes/{note_id}** - Delete a note
- **GET /api/notes/{note_id}/render** - Render markdown note to HTML (NEW)
- **POST /api/notes/preview** - Preview markdown rendering (NEW)

### Folders

- **GET /api/folders/** - List all folders (with optional root_id filter)
- **GET /api/folders/{id}** - Get a specific folder
- **GET /api/folders/tree/{root_id}** - Get folder tree hierarchy (NEW)
- **PUT /api/folders/{id}/note** - Update folder note
- **DELETE /api/folders/{id}/note** - Delete folder note

### Saved Searches

- **GET /api/saved-searches/** - List all saved searches
- **POST /api/saved-searches/** - Create a saved search
- **GET /api/saved-searches/{id}** - Get a specific saved search
- **PUT /api/saved-searches/{id}** - Update a saved search
- **DELETE /api/saved-searches/{id}** - Delete a saved search

### Search

- **POST /api/search/** - Advanced script search with filters:
  - query (name/path)
  - languages (array)
  - tags (array)
  - status (array)
  - root_ids (array)
  - owner (string) - NEW
  - environment (string) - NEW
  - classification (string) - NEW
  - min_size / max_size (integers) - NEW
  - modified_after / modified_before (datetime) - NEW
- **GET /api/search/stats** - Get statistics

### Full-Text Search (NEW)

- **POST /api/fts/** - Full-text search across script content and notes
- **POST /api/fts/rebuild** - Rebuild FTS index for all or specific root
- **GET /api/fts/status** - Get FTS index status and statistics

### Watch Mode (NEW)

- **POST /api/watch/start/{root_id}** - Start watching a folder root
- **POST /api/watch/stop/{root_id}** - Stop watching a folder root
- **GET /api/watch/status** - Get watch mode status for all roots
- **POST /api/watch/start-all** - Start watching all enabled roots
- **POST /api/watch/stop-all** - Stop all watchers

### Similarity Detection (NEW)

- **GET /api/similarity/{script_id}** - Find similar scripts (with threshold)
- **GET /api/similarity/groups/all** - Find all similarity groups
- **POST /api/similarity/matrix** - Generate similarity matrix for scripts
- **GET /api/similarity/compare/{id1}/{id2}** - Compare two specific scripts

### Attachments (NEW)

- **POST /api/attachments/upload** - Upload attachment (file + script_id or note_id)
- **GET /api/attachments/script/{script_id}** - List attachments for a script
- **GET /api/attachments/note/{note_id}** - List attachments for a note
- **GET /api/attachments/{id}** - Get attachment metadata
- **GET /api/attachments/{id}/download** - Download attachment file
- **DELETE /api/attachments/{id}** - Delete attachment
- **GET /api/attachments/stats/all** - Get attachment statistics

## Monitors

- **GET /api/monitors/** - List monitors, evaluating overdue status first
- **POST /api/monitors/** - Create a monitor (the response includes its ping key once)
- **GET/PUT/DELETE /api/monitors/{id}** - Read, update or delete a monitor
- **POST /api/monitors/{id}/pause** and **/resume** - Suspend or restore alerting
- **GET /api/monitors/{id}/ping-url** - Reveal the ping key deliberately
- **POST /api/monitors/ping/{ping_key}** - Record a heartbeat (unauthenticated)
- **GET /api/monitors/{id}/pings** - Ping history
- **GET /api/monitors/{id}/incidents** - Incidents raised for this monitor

Ping keys are omitted from listings; fetch one from the dedicated endpoint.

## Schedules

- **GET /api/schedules/** - List jobs
- **POST /api/schedules/** - Create a job. The cron expression and timezone are
  validated, and `next_run_at` is computed
- **GET/PUT/DELETE /api/schedules/{id}** - Read, update or delete a job
- **POST /api/schedules/{id}/enable** and **/disable**
- **POST /api/schedules/{id}/trigger** - Run immediately, outside the schedule
- **GET /api/schedules/{id}/executions** - Execution history
- **GET /api/schedules/{id}/executions/{execution_id}** - One execution with its logs
- **GET /api/schedules/{id}/metrics** - Duration and success-rate trends
- **GET /api/schedules/preview/cron** - Validate an expression and preview its next runs

Jobs are executed by the backend's own scheduler; no external cron is needed.

## Notifications

- **GET/POST /api/notifications/channels/** - List or create channels
- **GET /api/notifications/channels/types** - Config fields each channel type expects
- **GET/PUT/DELETE /api/notifications/channels/{id}**
- **POST /api/notifications/channels/{id}/test** - Send a real test message; the
  outcome is reported in the body as `{success, message}` rather than as an HTTP error
- **GET /api/notifications/incidents/** - List incidents (`status`, `source_type`, `limit`)
- **GET /api/notifications/incidents/stats** - Counts by status and severity
- **GET/PUT/DELETE /api/notifications/incidents/{id}**

Secret configuration values are always returned as `***`. Submitting `***` back
on an update preserves the stored value.

## Timestamps

All timestamps are returned in UTC with an explicit offset (for example
`2026-09-06T22:28:45Z`), so clients can render them in the viewer's own timezone
without guessing.

## Interactive Documentation

FastAPI serves the generated, always-current reference:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Treat those as authoritative; this file is a summary.
