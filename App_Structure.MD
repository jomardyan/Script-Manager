## Overview

The web app manages large collections of script files stored on disk, such as Python, PowerShell, Bash, and SQL. It indexes scripts from selected folders, stores metadata in a local SQLite database, and provides fast search, tagging, notes, and lifecycle management.

## Goals

* Provide a single place to catalog and organize many script files across multiple folders.
* Keep scripts on disk as the source of truth while storing management data in SQLite.
* Support recursive folder indexing with incremental updates.
* Enable quick retrieval through search, filters, and saved views.
* Track ownership, usage, and operational status for scripts.

## Target users

* Developers and DevOps engineers maintaining shared script libraries.
* IT administrators managing automation scripts across machines or shares.
* Teams curating internal utilities and runbooks.

## Supported script types

* Extension based detection with configurable mapping.
* Default extensions

  * Python .py
  * PowerShell .ps1 .psm1
  * Bash .sh
  * Batch .bat .cmd
  * SQL .sql
  * JavaScript .js
  * YAML .yml .yaml
  * JSON .json
  * Terraform .tf
* Shebang detection as an optional fallback for extensionless scripts.

## Core concepts

* Script file
  A file on disk with content and a stable identity derived from its full path plus file fingerprint.
* Folder root
  A user registered directory that can be scanned recursively.
* Index
  The database representation of files, folders, and metadata used for fast operations.
* Metadata
  Notes, tags, classification, ownership, status, and references that the app stores in SQLite.

## Primary workflows

### Add folder root and index scripts

* User selects a folder root to manage.
* User chooses indexing options

  * Recursive on or off
  * Include and exclude patterns
  * Follow symlinks on or off
  * Maximum file size limits
* App scans the folder

  * Discovers script files
  * Captures file metadata and fingerprints
  * Stores results in SQLite
* App displays indexing progress and results

  * New scripts
  * Updated scripts
  * Deleted or missing scripts

### Browse and manage scripts

* Folder tree view for folder roots and subfolders.
* Script list view with sorting and filters.
* Script detail view with

  * File path and basic metadata
  * Content preview with syntax highlighting
  * Notes and tags
  * Status and classification
  * Related links and references
  * Activity history

### Search at scale

* Global search across

  * File name
  * Path
  * Notes
  * Tags
  * Optional content indexing
* Faceted filters

  * Language or extension
  * Folder root
  * Status
  * Tags
  * Last modified date range
  * Size range
  * Owner
* Saved searches

  * Named queries with pinned filters
  * Shareable within the app instance

### Add notes and documentation

* Notes at script level

  * Free text notes
  * Markdown support as optional
  * Templates for common sections
* Folder level notes

  * Useful for describing collections and conventions
* Attachments as optional

  * Small files stored in a managed directory with database references

### Tagging and classification

* Tags

  * Free form tags
  * Tag groups as optional, such as environment, system, team
* Classification

  * Example values, production, staging, development, deprecated
* Risk and permission metadata

  * Example values, requires admin, destructive actions, safe to run

### Script lifecycle management

* Status tracking

  * Draft, active, deprecated, archived
* Deprecation workflow

  * Set deprecated date
  * Add migration note
  * Hide from default views
* Archival workflow

  * Mark as archived
  * Optionally exclude from content indexing

### Duplicate and drift detection

* Duplicate detection by content hash

  * Shows groups of identical scripts in different paths
* Similarity detection as optional

  * Basic heuristics such as normalized hashes or fuzzy matching
* Drift tracking

  * Shows changes across scans
  * Highlights significant metadata changes such as ownership or status

### Bulk operations

* Apply tags to selected scripts.
* Set status or classification in bulk.
* Move scripts between collections, meaning update folder root membership if applicable.
* Export metadata as JSON or CSV.

## Indexing and sync behavior

### Scan modes

* Full scan

  * Rebuilds index for selected roots.
* Incremental scan

  * Detects changes using file modification time and size.
  * Falls back to hashing when needed.
* Watch mode as optional

  * Uses filesystem notifications where available.
  * Falls back to periodic polling.

### Change handling

* New file

  * Create script record and initial fingerprint.
* Modified file

  * Update fingerprint and metadata.
  * Record change in history.
* Deleted or missing file

  * Mark as missing.
  * Keep metadata unless user purges.

### Performance approach for large repositories

* Store only required fields in list views.
* Use database indexes for path, name, tags, and timestamps.
* Cache derived values such as language and line count.
* Defer content indexing to an optional background job within the same local process.
* Support pagination everywhere.

## Functional requirements

### Script inventory

* Register multiple folder roots.
* Maintain script records with stable IDs.
* Track file path, size, timestamps, and language.
* Track content hash for duplicates and integrity.

### Notes and metadata

* Create and edit notes per script and per folder.
* Maintain tags with auto-complete.
* Maintain status, classification, owner, and environment fields.
* Maintain custom fields as key value pairs.

### Search and filters

* Provide fast search by name and path.
* Provide metadata search by tags, status, classification, and owner.
* Provide optional full text content search with SQLite FTS.

### Views and navigation

* Folder tree navigation.
* Script list with configurable columns.
* Script detail page with preview and metadata editing.
* Saved views and saved searches.

### Audit and history

* Record key actions

  * Note edits
  * Tag changes
  * Status changes
  * Folder root changes
  * Indexing events
* Show per script timeline.

### Import and export

* Export metadata for selected scripts.
* Import metadata from export file with conflict resolution

  * Prefer database values
  * Prefer import values
  * Merge tags and notes

### Safety and guardrails

* Read only by default.
* No script execution as a default capability.
* If execution is added later, require explicit enablement and logging.

## Local SQLite data storage

### Persistence model

* SQLite file stored locally on the host running the app.
* Filesystem paths stored as absolute paths.
* Script identity and change detection

  * Full path
  * Size
  * Modified time
  * Content hash

### Suggested tables

* folder_roots

  * id, path, recursive, include_patterns, exclude_patterns, last_scan_time
* folders

  * id, root_id, path, parent_id, note_id
* scripts

  * id, root_id, folder_id, path, name, extension, language, size, mtime, hash, missing_flag
* script_notes

  * id, script_id, content, updated_at
* tags

  * id, name, group_name
* script_tags

  * script_id, tag_id
* script_fields

  * script_id, key, value
* script_status

  * script_id, status, classification, owner, environment, updated_at
* scan_events

  * id, root_id, started_at, ended_at, counters, status
* change_log

  * id, script_id, event_time, change_type, old_value, new_value, actor

### Search indexing

* Use SQLite FTS5 for optional full text search across

  * Notes
  * File name and path
  * Script content if enabled
* Keep content indexing optional to control database size.

## Web app architecture

### Deployment model

* Single host, local only or LAN accessible.
* Backend service exposes an HTTP API.
* Frontend served by the backend or as a separate static bundle.
* SQLite accessed only by the backend process.

### Roles and access

* Single user mode as default.
* Multi user mode as optional

  * Local accounts or OS integrated auth depending on environment
  * Role based permissions, admin and editor and viewer

## Non functional requirements

### Performance

* Must handle at least 100,000 script files with acceptable list and search latency.
* Target response time

  * Common searches under 1 second on a typical developer workstation with SSD
* Support batching and pagination to avoid memory spikes.

### Reliability

* Database migrations are versioned and reversible where feasible.
* Automatic backups of the SQLite file on a schedule.
* Safe recovery if a scan is interrupted.

### Security

* Local file paths and notes treated as sensitive data.
* Protect API endpoints with authentication when not running in local only mode.
* Sanitize rendered content, especially notes in Markdown mode.

### Observability

* App level logs for scanning, indexing, and errors.
* Metrics as optional, such as scan duration and counts.

## Key screens

### Dashboard

* Folder roots summary and scan status.
* Recently updated scripts.
* Saved searches and pinned tags.

### Folder roots

* Add, edit, remove folder root.
* Trigger full scan or incremental scan.
* View include and exclude rules.

### Script list

* Columns, name, language, path, status, tags, last modified, last scanned.
* Bulk select and bulk actions.
* Quick preview panel.

### Script detail

* Metadata editor.
* Notes editor.
* Content preview.
* History timeline.
* Duplicate group if applicable.

## Assumptions and safe next steps

* This description assumes the app does not execute scripts. Execution can be added later with explicit controls.
* Next step is to define the minimum viable scope

  * Indexing plus notes plus tags plus search plus saved views
* Next step is to confirm the expected scale and usage patterns

  * Number of files
  * Typical folder depth
  * Whether content search is required
  * Single user or multi user
