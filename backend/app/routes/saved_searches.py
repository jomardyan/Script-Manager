"""
Saved Searches API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite
import json

from app.db.database import get_db
from app.models.schemas import SavedSearchCreate, SavedSearchResponse

router = APIRouter()

@router.get("/", response_model=List[SavedSearchResponse])
async def list_saved_searches(db: aiosqlite.Connection = Depends(get_db)):
    """List all saved searches"""
    async with db.execute(
        "SELECT * FROM saved_searches ORDER BY is_pinned DESC, name"
    ) as cursor:
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            # Parse JSON query_params
            item['query_params'] = json.loads(item['query_params'])
            results.append(item)
        return results

@router.post("/", response_model=SavedSearchResponse)
async def create_saved_search(
    search: SavedSearchCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new saved search"""
    try:
        # Serialize query_params to JSON
        query_params_json = json.dumps(search.query_params)
        
        cursor = await db.execute(
            """
            INSERT INTO saved_searches (name, description, query_params, is_pinned)
            VALUES (?, ?, ?, ?)
            """,
            (search.name, search.description, query_params_json, search.is_pinned)
        )
        await db.commit()
        
        async with db.execute(
            "SELECT * FROM saved_searches WHERE id = ?",
            (cursor.lastrowid,)
        ) as cursor:
            row = await cursor.fetchone()
            result = dict(row)
            result['query_params'] = json.loads(result['query_params'])
            return result
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Saved search with this name already exists")

@router.get("/{search_id}", response_model=SavedSearchResponse)
async def get_saved_search(search_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a specific saved search"""
    async with db.execute(
        "SELECT * FROM saved_searches WHERE id = ?",
        (search_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Saved search not found")
        result = dict(row)
        result['query_params'] = json.loads(result['query_params'])
        return result

@router.put("/{search_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    search_id: int,
    search: SavedSearchCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update a saved search"""
    async with db.execute(
        "SELECT id FROM saved_searches WHERE id = ?",
        (search_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Saved search not found")
    
    query_params_json = json.dumps(search.query_params)
    
    await db.execute(
        """
        UPDATE saved_searches
        SET name = ?, description = ?, query_params = ?, is_pinned = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (search.name, search.description, query_params_json, search.is_pinned, search_id)
    )
    await db.commit()
    
    async with db.execute(
        "SELECT * FROM saved_searches WHERE id = ?",
        (search_id,)
    ) as cursor:
        row = await cursor.fetchone()
        result = dict(row)
        result['query_params'] = json.loads(result['query_params'])
        return result

@router.delete("/{search_id}")
async def delete_saved_search(search_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a saved search"""
    async with db.execute(
        "SELECT id FROM saved_searches WHERE id = ?",
        (search_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Saved search not found")
    
    await db.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
    await db.commit()
    return {"message": "Saved search deleted successfully"}
