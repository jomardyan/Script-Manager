"""
Notes API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from app.db.database import get_db
from app.models.schemas import NoteCreate, NoteResponse

router = APIRouter()

@router.get("/script/{script_id}", response_model=List[NoteResponse])
async def get_script_notes(script_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get all notes for a script"""
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    async with db.execute(
        "SELECT * FROM script_notes WHERE script_id = ? ORDER BY updated_at DESC",
        (script_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

@router.post("/script/{script_id}", response_model=NoteResponse)
async def create_script_note(
    script_id: int,
    note: NoteCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new note for a script"""
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    cursor = await db.execute(
        "INSERT INTO script_notes (script_id, content) VALUES (?, ?)",
        (script_id, note.content)
    )
    await db.commit()
    
    async with db.execute(
        "SELECT * FROM script_notes WHERE id = ?",
        (cursor.lastrowid,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)

@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note: NoteCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update an existing note"""
    async with db.execute("SELECT id FROM script_notes WHERE id = ?", (note_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Note not found")
    
    await db.execute(
        "UPDATE script_notes SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (note.content, note_id)
    )
    await db.commit()
    
    async with db.execute(
        "SELECT * FROM script_notes WHERE id = ?",
        (note_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)

@router.delete("/{note_id}")
async def delete_note(note_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a note"""
    async with db.execute("SELECT id FROM script_notes WHERE id = ?", (note_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Note not found")
    
    await db.execute("DELETE FROM script_notes WHERE id = ?", (note_id,))
    await db.commit()
    return {"message": "Note deleted successfully"}
