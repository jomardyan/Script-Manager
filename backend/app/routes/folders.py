"""
Folders API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from app.db.database import get_db
from app.models.schemas import FolderResponse, FolderNoteUpdate

router = APIRouter()

@router.get("/", response_model=List[FolderResponse])
async def list_folders(
    root_id: int = None,
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all folders, optionally filtered by root"""
    if root_id:
        query = "SELECT * FROM folders WHERE root_id = ? ORDER BY path"
        params = (root_id,)
    else:
        query = "SELECT * FROM folders ORDER BY path"
        params = ()
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(folder_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a specific folder"""
    async with db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder not found")
        return dict(row)

@router.put("/{folder_id}/note")
async def update_folder_note(
    folder_id: int,
    note_update: FolderNoteUpdate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update or create a note for a folder"""
    # Check if folder exists
    async with db.execute("SELECT id FROM folders WHERE id = ?", (folder_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Folder not found")
    
    # Update the note
    await db.execute(
        "UPDATE folders SET note = ? WHERE id = ?",
        (note_update.note, folder_id)
    )
    await db.commit()
    
    return {"message": "Folder note updated successfully"}

@router.delete("/{folder_id}/note")
async def delete_folder_note(folder_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a folder note"""
    # Check if folder exists
    async with db.execute("SELECT id FROM folders WHERE id = ?", (folder_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Folder not found")
    
    # Clear the note
    await db.execute(
        "UPDATE folders SET note = NULL WHERE id = ?",
        (folder_id,)
    )
    await db.commit()
    
    return {"message": "Folder note deleted successfully"}
