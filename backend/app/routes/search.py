"""
Search API endpoints
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List
import aiosqlite

from app.db.database import get_db
from app.models.schemas import SearchRequest, PaginatedResponse

router = APIRouter()

@router.post("/", response_model=PaginatedResponse)
async def search_scripts(
    search: SearchRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Advanced search for scripts"""
    conditions = ["s.missing_flag = 0"]
    params = []
    
    # Query filter
    if search.query:
        conditions.append("(s.name LIKE ? OR s.path LIKE ?)")
        search_pattern = f"%{search.query}%"
        params.extend([search_pattern, search_pattern])
    
    # Language filter
    if search.languages:
        placeholders = ','.join('?' * len(search.languages))
        conditions.append(f"s.language IN ({placeholders})")
        params.extend(search.languages)
    
    # Status filter
    if search.status:
        placeholders = ','.join('?' * len(search.status))
        conditions.append(f"st.status IN ({placeholders})")
        params.extend(search.status)
    
    # Root ID filter
    if search.root_ids:
        placeholders = ','.join('?' * len(search.root_ids))
        conditions.append(f"s.root_id IN ({placeholders})")
        params.extend(search.root_ids)
    
    # Tags filter
    if search.tags:
        tag_conditions = []
        for tag in search.tags:
            tag_conditions.append("t.name = ?")
            params.append(tag)
        conditions.append(f"({' OR '.join(tag_conditions)})")
    
    # Owner filter
    if search.owner:
        conditions.append("st.owner = ?")
        params.append(search.owner)
    
    # Environment filter
    if search.environment:
        conditions.append("st.environment = ?")
        params.append(search.environment)
    
    # Classification filter
    if search.classification:
        conditions.append("st.classification = ?")
        params.append(search.classification)
    
    # Size range filters
    if search.min_size is not None:
        conditions.append("s.size >= ?")
        params.append(search.min_size)
    
    if search.max_size is not None:
        conditions.append("s.size <= ?")
        params.append(search.max_size)
    
    # Date range filters
    if search.modified_after:
        conditions.append("s.mtime >= ?")
        params.append(search.modified_after)
    
    if search.modified_before:
        conditions.append("s.mtime <= ?")
        params.append(search.modified_before)
    
    where_clause = " AND ".join(conditions)
    
    # Get total count
    count_query = f"""
        SELECT COUNT(DISTINCT s.id)
        FROM scripts s
        LEFT JOIN script_status st ON s.id = st.script_id
        LEFT JOIN script_tags sct ON s.id = sct.script_id
        LEFT JOIN tags t ON sct.tag_id = t.id
        WHERE {where_clause}
    """
    async with db.execute(count_query, params) as cursor:
        total = (await cursor.fetchone())[0]
    
    # Get paginated results
    offset = (search.page - 1) * search.page_size
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
    params.extend([search.page_size, offset])
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item['tags'] = item['tags'].split(',') if item.get('tags') else []
            items.append(item)
    
    total_pages = (total + search.page_size - 1) // search.page_size
    
    return {
        'items': items,
        'total': total,
        'page': search.page,
        'page_size': search.page_size,
        'total_pages': total_pages
    }

@router.get("/stats")
async def get_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Get statistics about scripts"""
    stats = {}
    
    # Total scripts
    async with db.execute(
        "SELECT COUNT(*) FROM scripts WHERE missing_flag = 0"
    ) as cursor:
        stats['total_scripts'] = (await cursor.fetchone())[0]
    
    # Scripts by language
    async with db.execute(
        """
        SELECT language, COUNT(*) as count
        FROM scripts
        WHERE missing_flag = 0 AND language IS NOT NULL
        GROUP BY language
        ORDER BY count DESC
        """
    ) as cursor:
        rows = await cursor.fetchall()
        stats['by_language'] = {row[0]: row[1] for row in rows}
    
    # Scripts by status
    async with db.execute(
        """
        SELECT st.status, COUNT(*) as count
        FROM scripts s
        LEFT JOIN script_status st ON s.id = st.script_id
        WHERE s.missing_flag = 0
        GROUP BY st.status
        """
    ) as cursor:
        rows = await cursor.fetchall()
        stats['by_status'] = {row[0] or 'unknown': row[1] for row in rows}
    
    # Total tags
    async with db.execute("SELECT COUNT(*) FROM tags") as cursor:
        stats['total_tags'] = (await cursor.fetchone())[0]
    
    # Total folder roots
    async with db.execute("SELECT COUNT(*) FROM folder_roots") as cursor:
        stats['total_roots'] = (await cursor.fetchone())[0]
    
    return stats
