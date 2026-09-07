"""
Notes API endpoints
"""
import html
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from app.db.database import get_db
from app.models.schemas import NoteCreate, NoteResponse
from app.services.fts import update_script_notes_fts
from app.services.markdown import render_markdown, extract_markdown_preview
from app.routes.deps import require_permission

router = APIRouter()

read_access = Depends(require_permission("notes.read"))
create_access = Depends(require_permission("notes.create"))
update_access = Depends(require_permission("notes.update"))
delete_access = Depends(require_permission("notes.delete"))

@router.get("/script/{script_id}", response_model=List[NoteResponse], dependencies=[read_access])
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

@router.post("/script/{script_id}", response_model=NoteResponse, status_code=201, dependencies=[create_access])
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
        "INSERT INTO script_notes (script_id, content, is_markdown) VALUES (?, ?, ?)",
        (script_id, note.content, note.is_markdown)
    )
    note_id = cursor.lastrowid
    
    # Log the change
    await db.execute(
        """
        INSERT INTO change_log (script_id, change_type, new_value)
        VALUES (?, 'note_added', ?)
        """,
        (script_id, note.content[:100])  # Store first 100 chars
    )
    
    await db.commit()
    await update_script_notes_fts(db, script_id)

    async with db.execute(
        "SELECT * FROM script_notes WHERE id = ?",
        (note_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)

@router.put("/{note_id}", response_model=NoteResponse, dependencies=[update_access])
async def update_note(
    note_id: int,
    note: NoteCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update an existing note"""
    async with db.execute(
        "SELECT script_id, content, is_markdown FROM script_notes WHERE id = ?",
        (note_id,)
    ) as cursor:
        note_row = await cursor.fetchone()
        if not note_row:
            raise HTTPException(status_code=404, detail="Note not found")
        script_id = note_row[0]
        old_content = note_row[1]
    
    await db.execute(
        "UPDATE script_notes SET content = ?, is_markdown = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (note.content, note.is_markdown, note_id)
    )
    
    # Log the change
    await db.execute(
        """
        INSERT INTO change_log (script_id, change_type, old_value, new_value)
        VALUES (?, 'note_updated', ?, ?)
        """,
        (script_id, old_content[:100], note.content[:100])
    )
    
    await db.commit()
    await update_script_notes_fts(db, script_id)

    async with db.execute(
        "SELECT * FROM script_notes WHERE id = ?",
        (note_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)

@router.delete("/{note_id}", dependencies=[delete_access])
async def delete_note(note_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a note"""
    async with db.execute(
        "SELECT script_id, content FROM script_notes WHERE id = ?",
        (note_id,)
    ) as cursor:
        note_row = await cursor.fetchone()
        if not note_row:
            raise HTTPException(status_code=404, detail="Note not found")
        script_id = note_row[0]
        old_content = note_row[1]
    
    from app.routes.attachments import purge_attachment_files

    await purge_attachment_files(db, note_ids=[note_id])
    await db.execute("DELETE FROM script_notes WHERE id = ?", (note_id,))
    
    # Log the change
    await db.execute(
        """
        INSERT INTO change_log (script_id, change_type, old_value)
        VALUES (?, 'note_deleted', ?)
        """,
        (script_id, old_content[:100])
    )
    
    await db.commit()
    await update_script_notes_fts(db, script_id)
    return {"message": "Note deleted successfully"}

@router.get("/{note_id}/render", dependencies=[read_access])
async def render_note(note_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Render a markdown note to HTML"""
    async with db.execute(
        "SELECT content, is_markdown FROM script_notes WHERE id = ?",
        (note_id,)
    ) as cursor:
        note_row = await cursor.fetchone()
        if not note_row:
            raise HTTPException(status_code=404, detail="Note not found")
        
        content, is_markdown = note_row
    
    if not is_markdown:
        # Escape before wrapping: the markdown path is sanitised by bleach, so
        # leaving the plain-text path raw made it the easier XSS route of the two.
        return {
            "html": f"<pre>{html.escape(content)}</pre>",
            "is_markdown": False,
            "preview": content[:200]
        }
    
    # Render markdown
    html = render_markdown(content, safe=True)
    preview = extract_markdown_preview(content)
    
    return {
        "html": html,
        "is_markdown": True,
        "preview": preview
    }

@router.post("/preview", dependencies=[read_access])
async def preview_markdown(note: NoteCreate):
    """Preview markdown rendering without saving"""
    if not note.is_markdown:
        return {
            "html": f"<pre>{html.escape(note.content)}</pre>",
            "is_markdown": False,
            "preview": note.content[:200]
        }
    
    html = render_markdown(note.content, safe=True)
    preview = extract_markdown_preview(note.content)
    
    return {
        "html": html,
        "is_markdown": True,
        "preview": preview
    }
