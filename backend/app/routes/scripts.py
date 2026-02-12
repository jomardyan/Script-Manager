"""
Scripts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
import aiosqlite

from app.db.database import get_db
from app.models.schemas import ScriptResponse, ScriptListResponse, StatusUpdate, PaginatedResponse

router = APIRouter()

@router.get("/", response_model=PaginatedResponse)
async def list_scripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    root_id: Optional[int] = None,
    language: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
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
        ORDER BY s.name
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
        "SELECT status FROM script_status WHERE script_id = ?",
        (script_id,)
    ) as cursor:
        status_row = await cursor.fetchone()
        script['status'] = status_row[0] if status_row else None
    
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
        await db.execute(
            "INSERT INTO script_tags (script_id, tag_id) VALUES (?, ?)",
            (script_id, tag_id)
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
    await db.execute(
        "DELETE FROM script_tags WHERE script_id = ? AND tag_id = ?",
        (script_id, tag_id)
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
