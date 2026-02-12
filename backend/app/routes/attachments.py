"""
Attachments API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from typing import List, Optional
import aiosqlite
import os
import uuid
from pathlib import Path
import mimetypes

from app.db.database import get_db
from app.models.schemas import AttachmentResponse

router = APIRouter()

# Attachments directory
ATTACHMENTS_DIR = os.getenv("ATTACHMENTS_DIR", "./data/attachments")
Path(ATTACHMENTS_DIR).mkdir(parents=True, exist_ok=True)

# Max file size (10MB)
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024


@router.post("/upload", response_model=AttachmentResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    script_id: Optional[int] = None,
    note_id: Optional[int] = None,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Upload an attachment file
    Can be attached to a script or a note
    """
    if not script_id and not note_id:
        raise HTTPException(status_code=400, detail="Must specify either script_id or note_id")
    
    # Verify script or note exists
    if script_id:
        async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Script not found")
    
    if note_id:
        async with db.execute("SELECT id FROM script_notes WHERE id = ?", (note_id,)) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Note not found")
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Check file size
    if file_size > MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_ATTACHMENT_SIZE / (1024*1024)}MB"
        )
    
    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(ATTACHMENTS_DIR, unique_filename)
    
    # Save file
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(file.filename)
    
    # Save to database
    cursor = await db.execute(
        """
        INSERT INTO attachments (script_id, note_id, filename, original_filename, 
                                file_path, file_size, mime_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (script_id, note_id, unique_filename, file.filename, file_path, file_size, mime_type)
    )
    await db.commit()
    
    # Return attachment details
    async with db.execute(
        "SELECT * FROM attachments WHERE id = ?",
        (cursor.lastrowid,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)


@router.get("/script/{script_id}", response_model=List[AttachmentResponse])
async def list_script_attachments(
    script_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all attachments for a script"""
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    async with db.execute(
        "SELECT * FROM attachments WHERE script_id = ? ORDER BY created_at DESC",
        (script_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.get("/note/{note_id}", response_model=List[AttachmentResponse])
async def list_note_attachments(
    note_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all attachments for a note"""
    async with db.execute("SELECT id FROM script_notes WHERE id = ?", (note_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Note not found")
    
    async with db.execute(
        "SELECT * FROM attachments WHERE note_id = ? ORDER BY created_at DESC",
        (note_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Download an attachment file"""
    async with db.execute(
        "SELECT file_path, original_filename, mime_type FROM attachments WHERE id = ?",
        (attachment_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")
        
        file_path, original_filename, mime_type = row
    
    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Attachment file not found on disk")
    
    # Return file
    return FileResponse(
        path=file_path,
        filename=original_filename,
        media_type=mime_type or 'application/octet-stream'
    )


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Get attachment metadata"""
    async with db.execute(
        "SELECT * FROM attachments WHERE id = ?",
        (attachment_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")
        return dict(row)


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Delete an attachment"""
    async with db.execute(
        "SELECT file_path FROM attachments WHERE id = ?",
        (attachment_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")
        
        file_path = row[0]
    
    # Delete file from disk
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Error deleting attachment file: {e}")
    
    # Delete from database
    await db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    await db.commit()
    
    return {"message": "Attachment deleted successfully"}


@router.get("/stats/all")
async def get_attachment_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Get attachment statistics"""
    # Count total attachments
    async with db.execute("SELECT COUNT(*), SUM(file_size) FROM attachments") as cursor:
        row = await cursor.fetchone()
        total_count = row[0]
        total_size = row[1] or 0
    
    # Count by type
    async with db.execute(
        """
        SELECT mime_type, COUNT(*), SUM(file_size)
        FROM attachments
        GROUP BY mime_type
        ORDER BY COUNT(*) DESC
        """
    ) as cursor:
        types = await cursor.fetchall()
        by_type = [
            {
                'mime_type': t[0] or 'unknown',
                'count': t[1],
                'total_size': t[2]
            }
            for t in types
        ]
    
    return {
        'total_attachments': total_count,
        'total_size_bytes': total_size,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'by_type': by_type
    }
