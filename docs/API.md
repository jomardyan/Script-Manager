# Script Manager API Documentation

## Base URL

```
http://localhost:8000/api
```

## Endpoints

### Health Check

**GET /health** - Returns API health status

### Folder Roots

- **GET /api/folder-roots/** - List all folder roots
- **POST /api/folder-roots/** - Create a new folder root
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
- **POST /api/notes/script/{script_id}** - Create a note
- **PUT /api/notes/{note_id}** - Update a note
- **DELETE /api/notes/{note_id}** - Delete a note

### Folders

- **GET /api/folders/** - List all folders (NEW)
- **GET /api/folders/{id}** - Get a specific folder (NEW)
- **PUT /api/folders/{id}/note** - Update folder note (NEW)
- **DELETE /api/folders/{id}/note** - Delete folder note (NEW)

### Saved Searches

- **GET /api/saved-searches/** - List all saved searches (NEW)
- **POST /api/saved-searches/** - Create a saved search (NEW)
- **GET /api/saved-searches/{id}** - Get a specific saved search (NEW)
- **PUT /api/saved-searches/{id}** - Update a saved search (NEW)
- **DELETE /api/saved-searches/{id}** - Delete a saved search (NEW)

### Search

- **POST /api/search/** - Advanced script search
- **GET /api/search/stats** - Get statistics

## Interactive Documentation

FastAPI provides interactive API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
