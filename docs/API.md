# Script Manager API Documentation

## Base URL

```
http://localhost:8000/api
```

## Endpoints

### Health Check

**GET /health** - Returns API health status

### Authentication (NEW)

- **POST /api/auth/login** - Login and get JWT token
- **GET /api/auth/me** - Get current user info
- **POST /api/auth/register** - Register new user
- **PUT /api/auth/change-password** - Change password

### Folder Roots

- **GET /api/folder-roots/** - List all folder roots
- **POST /api/folder-roots/** - Create a new folder root (with enable_content_indexing, enable_watch_mode)
- **GET /api/folder-roots/{id}** - Get a specific folder root
- **DELETE /api/folder-roots/{id}** - Delete a folder root
- **POST /api/folder-roots/{id}/scan** - Scan a folder root for scripts

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

## Interactive Documentation

FastAPI provides interactive API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Authentication

For protected endpoints, include JWT token in header:
```
Authorization: Bearer <your_jwt_token>
```

Get token via POST /api/auth/login

## Total Endpoints: 73

- Core Features: 41 endpoints
- Optional Features: 32 endpoints
