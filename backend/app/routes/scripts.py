"""
Scripts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
import os
import aiosqlite

from app.db.database import get_db
from app.models.schemas import (
    ScriptResponse, StatusUpdate, PaginatedResponse,
    BulkTagRequest, BulkStatusRequest
)

router = APIRouter()


@router.get("/", response_model=PaginatedResponse)
async def list_scripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    root_id: Optional[int] = None,
    language: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    db: aiosqlite.Connection = Depends(get_db)
):
    """List scripts with pagination and filters"""
    conditions = ["s.missing_flag = 0"]
    params = []
    
    if root_id:
        conditions.append("s.root_id = ?")
        params.append(root_id)
    
    if language:
        conditions.append("s.language = ?")
        params.append(language)
    
    if status:
        conditions.append("st.status = ?")
        params.append(status)
    
    if search:
        conditions.append("(s.name LIKE ? OR s.path LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern])

    allowed_sort_columns = {
        "name": "s.name",
        "path": "s.path",
        "language": "s.language",
        "size": "s.size",
        "mtime": "s.mtime",
        "status": "st.status",
    }
    sort_column = allowed_sort_columns.get(sort_by.lower())
    if not sort_column:
        raise HTTPException(status_code=400, detail="Invalid sort_by value")

    sort_direction = sort_order.upper()
    if sort_direction not in {"ASC", "DESC"}:
        raise HTTPException(status_code=400, detail="Invalid sort_order value")

    where_clause = " AND ".join(conditions)
    
    # Get total count
    count_query = f"""
        SELECT COUNT(DISTINCT s.id)
        FROM scripts s
        LEFT JOIN script_status st ON s.id = st.script_id
        WHERE {where_clause}
    """
    async with db.execute(count_query, params) as cursor:
        total = (await cursor.fetchone())[0]
    
    # Get paginated results
    offset = (page - 1) * page_size
    query = f"""
        SELECT DISTINCT s.id, s.name, s.path, s.extension, s.language, 
               s.size, s.mtime, st.status,
               GROUP_CONCAT(DISTINCT t.name) as tags
        FROM scripts s
        LEFT JOIN script_status st ON s.id = st.script_id
        LEFT JOIN script_tags sct ON s.id = sct.script_id
        LEFT JOIN tags t ON sct.tag_id = t.id
        WHERE {where_clause}
        GROUP BY s.id
        ORDER BY {sort_column} {sort_direction}, s.id ASC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item['tags'] = item['tags'].split(',') if item.get('tags') else []
            items.append(item)
    
    total_pages = (total + page_size - 1) // page_size
    
    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages
    }

@router.get("/{script_id}", response_model=ScriptResponse)
async def get_script(script_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get detailed script information"""
    async with db.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Script not found")
        script = dict(row)
    
    # Get tags
    async with db.execute(
        """
        SELECT t.name FROM tags t
        JOIN script_tags st ON t.id = st.tag_id
        WHERE st.script_id = ?
        """,
        (script_id,)
    ) as cursor:
        tags = [row[0] for row in await cursor.fetchall()]
    script['tags'] = tags
    
    # Get status
    async with db.execute(
        """
        SELECT status, classification, owner, environment, deprecated_date, migration_note
        FROM script_status
        WHERE script_id = ?
        """,
        (script_id,)
    ) as cursor:
        status_row = await cursor.fetchone()
        if status_row:
            script['status'] = status_row[0]
            script['classification'] = status_row[1]
            script['owner'] = status_row[2]
            script['environment'] = status_row[3]
            script['deprecated_date'] = status_row[4]
            script['migration_note'] = status_row[5]
        else:
            script['status'] = None
            script['classification'] = None
            script['owner'] = None
            script['environment'] = None
            script['deprecated_date'] = None
            script['migration_note'] = None
    
    # Get notes
    async with db.execute(
        "SELECT content FROM script_notes WHERE script_id = ? ORDER BY updated_at DESC LIMIT 1",
        (script_id,)
    ) as cursor:
        note_row = await cursor.fetchone()
        script['notes'] = note_row[0] if note_row else None
    
    return script

@router.put("/{script_id}/status")
async def update_script_status(
    script_id: int,
    status_update: StatusUpdate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update script status and classification"""
    # Check if script exists
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    # Get old values for change log
    old_values = {}
    async with db.execute(
        "SELECT status, classification, owner, environment FROM script_status WHERE script_id = ?",
        (script_id,)
    ) as cursor:
        old_row = await cursor.fetchone()
        if old_row:
            old_values = {
                'status': old_row[0],
                'classification': old_row[1],
                'owner': old_row[2],
                'environment': old_row[3]
            }
    
    # Check if status record exists
    exists = bool(old_values)
    
    if exists:
        # Update existing status
        update_fields = []
        params = []
        
        if status_update.status is not None:
            update_fields.append("status = ?")
            params.append(status_update.status)
        if status_update.classification is not None:
            update_fields.append("classification = ?")
            params.append(status_update.classification)
        if status_update.owner is not None:
            update_fields.append("owner = ?")
            params.append(status_update.owner)
        if status_update.environment is not None:
            update_fields.append("environment = ?")
            params.append(status_update.environment)
        if status_update.deprecated_date is not None:
            update_fields.append("deprecated_date = ?")
            params.append(status_update.deprecated_date)
        if status_update.migration_note is not None:
            update_fields.append("migration_note = ?")
            params.append(status_update.migration_note)
        
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(script_id)
            query = f"UPDATE script_status SET {', '.join(update_fields)} WHERE script_id = ?"
            await db.execute(query, params)
    else:
        # Insert new status
        await db.execute(
            """
            INSERT INTO script_status (script_id, status, classification, owner, 
                                      environment, deprecated_date, migration_note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                script_id,
                status_update.status or 'active',
                status_update.classification,
                status_update.owner,
                status_update.environment,
                status_update.deprecated_date,
                status_update.migration_note
            )
        )
    
    # Log status changes
    if status_update.status is not None:
        await db.execute(
            """
            INSERT INTO change_log (script_id, change_type, old_value, new_value)
            VALUES (?, 'status_changed', ?, ?)
            """,
            (script_id, old_values.get('status', 'none'), status_update.status)
        )
    
    if status_update.classification is not None:
        await db.execute(
            """
            INSERT INTO change_log (script_id, change_type, old_value, new_value)
            VALUES (?, 'classification_changed', ?, ?)
            """,
            (script_id, old_values.get('classification', 'none'), status_update.classification)
        )
    
    if status_update.owner is not None:
        await db.execute(
            """
            INSERT INTO change_log (script_id, change_type, old_value, new_value)
            VALUES (?, 'owner_changed', ?, ?)
            """,
            (script_id, old_values.get('owner', 'none'), status_update.owner)
        )
    
    if status_update.environment is not None:
        await db.execute(
            """
            INSERT INTO change_log (script_id, change_type, old_value, new_value)
            VALUES (?, 'environment_changed', ?, ?)
            """,
            (script_id, old_values.get('environment', 'none'), status_update.environment)
        )
    
    await db.commit()
    return {"message": "Status updated successfully"}

@router.post("/{script_id}/tags/{tag_id}")
async def add_tag_to_script(
    script_id: int,
    tag_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Add a tag to a script"""
    try:
        # Get tag name
        async with db.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)) as cursor:
            tag_row = await cursor.fetchone()
            tag_name = tag_row[0] if tag_row else str(tag_id)
        
        await db.execute(
            "INSERT INTO script_tags (script_id, tag_id) VALUES (?, ?)",
            (script_id, tag_id)
        )
        
        # Log the change
        await db.execute(
            """
            INSERT INTO change_log (script_id, change_type, new_value)
            VALUES (?, 'tag_added', ?)
            """,
            (script_id, tag_name)
        )
        
        await db.commit()
        return {"message": "Tag added successfully"}
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Tag already added to script")

@router.delete("/{script_id}/tags/{tag_id}")
async def remove_tag_from_script(
    script_id: int,
    tag_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Remove a tag from a script"""
    # Get tag name
    async with db.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)) as cursor:
        tag_row = await cursor.fetchone()
        tag_name = tag_row[0] if tag_row else str(tag_id)
    
    await db.execute(
        "DELETE FROM script_tags WHERE script_id = ? AND tag_id = ?",
        (script_id, tag_id)
    )
    
    # Log the change
    await db.execute(
        """
        INSERT INTO change_log (script_id, change_type, old_value)
        VALUES (?, 'tag_removed', ?)
        """,
        (script_id, tag_name)
    )
    
    await db.commit()
    return {"message": "Tag removed successfully"}

@router.get("/duplicates/list")
async def list_duplicates(db: aiosqlite.Connection = Depends(get_db)):
    """Find and list duplicate scripts"""
    query = """
        SELECT hash, COUNT(*) as count, GROUP_CONCAT(path, '|') as paths,
               GROUP_CONCAT(id, '|') as ids
        FROM scripts
        WHERE hash IS NOT NULL AND hash != '' AND missing_flag = 0
        GROUP BY hash
        HAVING count > 1
        ORDER BY count DESC
    """
    
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()
        duplicates = []
        for row in rows:
            duplicates.append({
                'hash': row[0],
                'count': row[1],
                'paths': row[2].split('|') if row[2] else [],
                'ids': [int(i) for i in row[3].split('|')] if row[3] else []
            })
        return duplicates

@router.get("/{script_id}/history")
async def get_script_history(script_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get change history for a script"""
    # Check if script exists
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    query = """
        SELECT id, event_time, change_type, old_value, new_value, actor
        FROM change_log
        WHERE script_id = ?
        ORDER BY event_time DESC
    """
    
    async with db.execute(query, (script_id,)) as cursor:
        rows = await cursor.fetchall()
        history = []
        for row in rows:
            history.append({
                'id': row[0],
                'event_time': row[1],
                'change_type': row[2],
                'old_value': row[3],
                'new_value': row[4],
                'actor': row[5]
            })
        return history

@router.get("/{script_id}/content")
async def get_script_content(script_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get the actual file content of a script"""
    # Get script path and validate it exists in database
    async with db.execute(
        "SELECT path, root_id FROM scripts WHERE id = ?",
        (script_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Script not found")
        file_path = row[0]
        root_id = row[1]
    
    # Get root path to validate the script is within a registered folder root
    async with db.execute(
        "SELECT path FROM folder_roots WHERE id = ?",
        (root_id,)
    ) as cursor:
        root_row = await cursor.fetchone()
        if not root_row:
            raise HTTPException(status_code=404, detail="Folder root not found")
        root_path = root_row[0]
    
    # Validate that the file path starts with the root path (security check)
    file_path_abs = os.path.abspath(file_path)
    root_path_abs = os.path.abspath(root_path)
    
    try:
        common_path = os.path.commonpath([file_path_abs, root_path_abs])
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: invalid file path")

    if common_path != root_path_abs:
        raise HTTPException(status_code=403, detail="Access denied: file is outside registered folder root")
    
    # Read file content
    try:
        with open(file_path_abs, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return {"content": content, "path": file_path}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found on disk")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@router.post("/bulk/tags")
async def bulk_add_tags(
    request: BulkTagRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Add tags to multiple scripts"""
    added_count = 0
    skipped_count = 0
    
    for script_id in request.script_ids:
        # Verify script exists
        async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
            if not await cursor.fetchone():
                skipped_count += 1
                continue
        
        for tag_id in request.tag_ids:
            try:
                # Get tag name for logging
                async with db.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)) as cursor:
                    tag_row = await cursor.fetchone()
                    tag_name = tag_row[0] if tag_row else str(tag_id)
                
                await db.execute(
                    "INSERT INTO script_tags (script_id, tag_id) VALUES (?, ?)",
                    (script_id, tag_id)
                )
                
                # Log the change
                await db.execute(
                    """
                    INSERT INTO change_log (script_id, change_type, new_value)
                    VALUES (?, 'tag_added_bulk', ?)
                    """,
                    (script_id, tag_name)
                )
                added_count += 1
            except aiosqlite.IntegrityError:
                # Tag already exists, skip
                skipped_count += 1
                continue
    
    await db.commit()
    return {
        "message": "Bulk tag operation completed",
        "added": added_count,
        "skipped": skipped_count
    }

@router.post("/bulk/status")
async def bulk_update_status(
    request: BulkStatusRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update status for multiple scripts"""
    updated_count = 0
    
    for script_id in request.script_ids:
        # Verify script exists
        async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
            if not await cursor.fetchone():
                continue
        
        # Check if status record exists
        async with db.execute(
            "SELECT script_id FROM script_status WHERE script_id = ?",
            (script_id,)
        ) as cursor:
            exists = await cursor.fetchone()
        
        if exists:
            # Update existing status
            update_fields = []
            params = []
            
            if request.status is not None:
                update_fields.append("status = ?")
                params.append(request.status)
            if request.classification is not None:
                update_fields.append("classification = ?")
                params.append(request.classification)
            if request.owner is not None:
                update_fields.append("owner = ?")
                params.append(request.owner)
            if request.environment is not None:
                update_fields.append("environment = ?")
                params.append(request.environment)
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(script_id)
                query = f"UPDATE script_status SET {', '.join(update_fields)} WHERE script_id = ?"
                await db.execute(query, params)
        else:
            # Insert new status
            await db.execute(
                """
                INSERT INTO script_status (script_id, status, classification, owner, environment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    script_id,
                    request.status or 'active',
                    request.classification,
                    request.owner,
                    request.environment
                )
            )
        
        # Log the change
        if request.status is not None:
            await db.execute(
                """
                INSERT INTO change_log (script_id, change_type, new_value)
                VALUES (?, 'status_changed_bulk', ?)
                """,
                (script_id, request.status)
            )
        
        updated_count += 1
    
    await db.commit()
    return {
        "message": "Bulk status update completed",
        "updated": updated_count
    }

@router.post("/export")
async def export_scripts(
    script_ids: List[int] = None,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Export script metadata as JSON"""
    # Build query based on whether specific script IDs are provided
    if script_ids:
        placeholders = ','.join('?' * len(script_ids))
        query = f"""
            SELECT id, root_id, folder_id, path, name, extension, language, 
                   size, mtime, hash, line_count, missing_flag, created_at, updated_at
            FROM scripts WHERE id IN ({placeholders})
        """
        params = script_ids
    else:
        query = """
            SELECT id, root_id, folder_id, path, name, extension, language,
                   size, mtime, hash, line_count, missing_flag, created_at, updated_at
            FROM scripts WHERE missing_flag = 0
        """
        params = ()
    
    exported_scripts = []
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        for row in rows:
            script = dict(row)
            script_id = script['id']
            
            # Get tags
            async with db.execute(
                """
                SELECT t.name, t.group_name, t.color
                FROM tags t
                JOIN script_tags st ON t.id = st.tag_id
                WHERE st.script_id = ?
                """,
                (script_id,)
            ) as tag_cursor:
                tags = [dict(tag_row) for tag_row in await tag_cursor.fetchall()]
            script['tags'] = tags
            
            # Get status
            async with db.execute(
                "SELECT * FROM script_status WHERE script_id = ?",
                (script_id,)
            ) as status_cursor:
                status_row = await status_cursor.fetchone()
                script['status'] = dict(status_row) if status_row else None
            
            # Get notes
            async with db.execute(
                "SELECT content, updated_at FROM script_notes WHERE script_id = ? ORDER BY updated_at DESC",
                (script_id,)
            ) as notes_cursor:
                notes = [dict(note_row) for note_row in await notes_cursor.fetchall()]
            script['notes'] = notes
            
            # Get custom fields
            async with db.execute(
                "SELECT key, value FROM script_fields WHERE script_id = ?",
                (script_id,)
            ) as fields_cursor:
                fields = {row[0]: row[1] for row in await fields_cursor.fetchall()}
            script['custom_fields'] = fields
            
            exported_scripts.append(script)
    
    return {
        "export_date": datetime.now().isoformat(),
        "script_count": len(exported_scripts),
        "scripts": exported_scripts
    }

@router.post("/import")
async def import_scripts(
    data: dict,
    conflict_resolution: str = Query("skip", regex="^(skip|overwrite|merge)$"),
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Import script metadata from export file
    conflict_resolution:
      - skip: Skip scripts that already exist
      - overwrite: Overwrite existing script metadata
      - merge: Merge tags and notes
    """
    imported_count = 0
    skipped_count = 0
    updated_count = 0
    
    scripts = data.get('scripts', [])
    
    for script_data in scripts:
        path = script_data.get('path')
        if not path:
            skipped_count += 1
            continue
        
        # Check if script exists
        async with db.execute(
            "SELECT id FROM scripts WHERE path = ?",
            (path,)
        ) as cursor:
            existing_row = await cursor.fetchone()
            existing_id = existing_row[0] if existing_row else None
        
        if existing_id:
            if conflict_resolution == "skip":
                skipped_count += 1
                continue
            
            # Handle tags
            if script_data.get('tags'):
                if conflict_resolution == "merge":
                    # Get existing tags
                    async with db.execute(
                        "SELECT tag_id FROM script_tags WHERE script_id = ?",
                        (existing_id,)
                    ) as cursor:
                        existing_tag_ids = {row[0] for row in await cursor.fetchall()}
                
                for tag_info in script_data['tags']:
                    tag_name = tag_info.get('name')
                    if tag_name:
                        # Find or create tag
                        async with db.execute(
                            "SELECT id FROM tags WHERE name = ?",
                            (tag_name,)
                        ) as cursor:
                            tag_row = await cursor.fetchone()
                            if tag_row:
                                tag_id = tag_row[0]
                            else:
                                cursor = await db.execute(
                                    "INSERT INTO tags (name, group_name, color) VALUES (?, ?, ?)",
                                    (tag_name, tag_info.get('group_name'), tag_info.get('color'))
                                )
                                tag_id = cursor.lastrowid
                        
                        # Add tag to script if not exists
                        if conflict_resolution == "overwrite" or tag_id not in existing_tag_ids:
                            try:
                                await db.execute(
                                    "INSERT INTO script_tags (script_id, tag_id) VALUES (?, ?)",
                                    (existing_id, tag_id)
                                )
                            except aiosqlite.IntegrityError:
                                # Tag already exists for this script, skip
                                pass
            
            # Handle status
            if script_data.get('status') and conflict_resolution in ["overwrite", "merge"]:
                status_data = script_data['status']
                await db.execute(
                    """
                    INSERT OR REPLACE INTO script_status 
                    (script_id, status, classification, owner, environment, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        existing_id,
                        status_data.get('status'),
                        status_data.get('classification'),
                        status_data.get('owner'),
                        status_data.get('environment')
                    )
                )
            
            # Handle notes
            if script_data.get('notes') and conflict_resolution == "merge":
                for note_data in script_data['notes']:
                    content = note_data.get('content')
                    if content:
                        is_markdown = 1 if note_data.get('is_markdown') else 0
                        await db.execute(
                            "INSERT INTO script_notes (script_id, content, is_markdown) VALUES (?, ?, ?)",
                            (existing_id, content, is_markdown)
                        )
            
            updated_count += 1
        else:
            # Script doesn't exist, skip (can't create without file on disk)
            skipped_count += 1
    
    await db.commit()
    
    return {
        "message": "Import completed",
        "imported": imported_count,
        "updated": updated_count,
        "skipped": skipped_count
    }

@router.get("/{script_id}/fields")
async def get_script_custom_fields(script_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get all custom fields for a script"""
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    async with db.execute(
        "SELECT key, value FROM script_fields WHERE script_id = ?",
        (script_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

@router.put("/{script_id}/fields/{key}")
async def set_script_custom_field(
    script_id: int,
    key: str,
    value: dict,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Set a custom field for a script"""
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    field_value = value.get('value', '')
    
    # Insert or replace the field
    await db.execute(
        """
        INSERT INTO script_fields (script_id, key, value)
        VALUES (?, ?, ?)
        ON CONFLICT(script_id, key) DO UPDATE SET value = excluded.value
        """,
        (script_id, key, field_value)
    )
    
    # Log the change
    await db.execute(
        """
        INSERT INTO change_log (script_id, change_type, new_value)
        VALUES (?, 'custom_field_updated', ?)
        """,
        (script_id, f"{key}={field_value}")
    )
    
    await db.commit()
    return {"message": "Custom field updated successfully"}

@router.delete("/{script_id}/fields/{key}")
async def delete_script_custom_field(
    script_id: int,
    key: str,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Delete a custom field from a script"""
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    await db.execute(
        "DELETE FROM script_fields WHERE script_id = ? AND key = ?",
        (script_id, key)
    )
    
    # Log the change
    await db.execute(
        """
        INSERT INTO change_log (script_id, change_type, old_value)
        VALUES (?, 'custom_field_deleted', ?)
        """,
        (script_id, key)
    )
    
    await db.commit()
    return {"message": "Custom field deleted successfully"}
