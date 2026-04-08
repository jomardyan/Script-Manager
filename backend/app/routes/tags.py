"""
Tags API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from app.db.database import get_db
from app.models.schemas import TagCreate, TagResponse

router = APIRouter()

@router.get("/", response_model=List[TagResponse])
async def list_tags(db: aiosqlite.Connection = Depends(get_db)):
    """List all tags"""
    async with db.execute("SELECT * FROM tags ORDER BY name") as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

@router.post("/", response_model=TagResponse)
async def create_tag(tag: TagCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new tag"""
    try:
        cursor = await db.execute(
            "INSERT INTO tags (name, group_name, color) VALUES (?, ?, ?)",
            (tag.name, tag.group_name, tag.color)
        )
        await db.commit()
        
        async with db.execute(
            "SELECT * FROM tags WHERE id = ?",
            (cursor.lastrowid,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row)
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")

@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a specific tag"""
    async with db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tag not found")
        return dict(row)

@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a tag"""
    async with db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Tag not found")
    
    await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    await db.commit()
    return {"message": "Tag deleted successfully"}

@router.get("/{tag_id}/scripts")
async def get_tag_scripts(
    tag_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Get all scripts with a specific tag"""
    async with db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Tag not found")
    
    query = """
        SELECT s.id, s.name, s.path, s.language
        FROM scripts s
        JOIN script_tags st ON s.id = st.script_id
        WHERE st.tag_id = ? AND s.missing_flag = 0
        ORDER BY s.name
    """
    async with db.execute(query, (tag_id,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
