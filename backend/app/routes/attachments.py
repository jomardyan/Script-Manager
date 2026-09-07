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
import logging
import mimetypes
import time

from app.db.database import get_db
from app.models.schemas import AttachmentResponse
from app.routes.deps import require_permission

logger = logging.getLogger(__name__)

router = APIRouter()

read_access = Depends(require_permission("attachments.read"))
upload_access = Depends(require_permission("attachments.upload"))
delete_access = Depends(require_permission("attachments.delete"))

# Attachments directory
ATTACHMENTS_DIR = os.getenv("ATTACHMENTS_DIR", "./data/attachments")
Path(ATTACHMENTS_DIR).mkdir(parents=True, exist_ok=True)

# Max file size (configurable; 10MB default)
MAX_ATTACHMENT_SIZE = int(os.getenv("MAX_ATTACHMENT_SIZE", str(10 * 1024 * 1024)))
CHUNK_SIZE = 64 * 1024
# Files younger than this are never pruned; see prune_orphaned_files.
PRUNE_MIN_AGE_SECONDS = int(os.getenv("ATTACHMENT_PRUNE_MIN_AGE", str(3600)))

# Extensions that are safe to preserve on the stored file. Anything else is
# saved without an extension so the file can never be served as active content.
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".log", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".ini",
    ".conf", ".cfg", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp",
    ".zip", ".gz", ".tar", ".tgz", ".7z",
    ".py", ".sh", ".ps1", ".psm1", ".sql", ".js", ".ts", ".bat", ".cmd", ".rb", ".pl",
}


def _safe_original_name(filename: Optional[str]) -> str:
    """Strip any directory components a client may have put in the filename."""
    name = os.path.basename((filename or "").replace("\\", "/").strip()) or "attachment"
    # Windows-style paths and stray separators are handled above; drop control
    # characters that would corrupt the Content-Disposition header on download.
    return "".join(ch for ch in name if ch.isprintable())[:255] or "attachment"


def _safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_EXTENSIONS else ""


@router.post("/upload", response_model=AttachmentResponse, status_code=201,
             dependencies=[upload_access])
async def upload_attachment(
    file: UploadFile = File(...),
    script_id: Optional[int] = None,
    note_id: Optional[int] = None,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Upload an attachment file.
    Can be attached to a script or a note.

    The upload is streamed to disk in chunks and aborted as soon as it exceeds
    the size limit, so a large upload cannot exhaust memory before the check.
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

    original_filename = _safe_original_name(file.filename)

    # The stored name is a random UUID, so a filename like "../../etc/passwd"
    # can never influence where the file lands; only the extension is reused
    # and it is validated against an allowlist first.
    file_extension = _safe_extension(original_filename)
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    file_path = os.path.join(ATTACHMENTS_DIR, unique_filename)

    file_size = 0
    try:
        with open(file_path, "wb") as fh:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_ATTACHMENT_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is "
                               f"{MAX_ATTACHMENT_SIZE // (1024 * 1024)}MB",
                    )
                fh.write(chunk)
    except Exception:
        # Never leave a partial file behind when the upload is rejected.
        try:
            os.remove(file_path)
        except OSError:
            pass
        raise

    if file_size == 0:
        try:
            os.remove(file_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    mime_type, _ = mimetypes.guess_type(original_filename)

    cursor = await db.execute(
        """
        INSERT INTO attachments (script_id, note_id, filename, original_filename, 
                                file_path, file_size, mime_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (script_id, note_id, unique_filename, original_filename, file_path, file_size, mime_type)
    )
    await db.commit()

    async with db.execute(
        "SELECT * FROM attachments WHERE id = ?",
        (cursor.lastrowid,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)


@router.get("/script/{script_id}", response_model=List[AttachmentResponse], dependencies=[read_access])
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


@router.get("/note/{note_id}", response_model=List[AttachmentResponse], dependencies=[read_access])
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


@router.get("/{attachment_id}/download", dependencies=[read_access])
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


@router.get("/{attachment_id}", response_model=AttachmentResponse, dependencies=[read_access])
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


@router.delete("/{attachment_id}", dependencies=[delete_access])
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
    except OSError as e:
        logger.warning("Error deleting attachment file %s: %s", file_path, e)
    
    # Delete from database
    await db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    await db.commit()
    
    return {"message": "Attachment deleted successfully"}


async def purge_attachment_files(db, *, script_ids=None, note_ids=None):
    """
    Delete the on-disk files for attachments belonging to the given parents.

    The database rows disappear via ON DELETE CASCADE, but the files they point
    at have no such relationship and were left behind forever.
    """
    clauses, params = [], []
    if script_ids:
        clauses.append(f"script_id IN ({','.join('?' * len(script_ids))})")
        params.extend(script_ids)
    if note_ids:
        clauses.append(f"note_id IN ({','.join('?' * len(note_ids))})")
        params.extend(note_ids)
    if not clauses:
        return 0

    async with db.execute(
        f"SELECT file_path FROM attachments WHERE {' OR '.join(clauses)}", tuple(params)
    ) as cursor:
        rows = await cursor.fetchall()

    removed = 0
    for row in rows:
        try:
            if row[0] and os.path.exists(row[0]):
                os.remove(row[0])
                removed += 1
        except OSError as exc:
            logger.warning("Could not delete attachment file %s: %s", row[0], exc)
    return removed


@router.post("/maintenance/prune", dependencies=[delete_access])
async def prune_orphaned_files(db: aiosqlite.Connection = Depends(get_db)):
    """
    Delete files in the attachments directory that no attachment row references.

    Cleans up after deletes that happened before parent cascades removed the
    files, and after any interrupted upload.
    """
    async with db.execute("SELECT filename FROM attachments") as cursor:
        known = {row[0] for row in await cursor.fetchall()}

    removed, freed = 0, 0
    try:
        entries = os.listdir(ATTACHMENTS_DIR)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read attachments directory: {exc}")

    # An upload writes its file before inserting the row that names it, so a
    # file younger than this window may simply be an upload still in progress.
    cutoff = time.time() - PRUNE_MIN_AGE_SECONDS

    for name in entries:
        if name in known:
            continue
        path = os.path.join(ATTACHMENTS_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) > cutoff:
                continue
        except OSError:
            continue
        try:
            freed += os.path.getsize(path)
            os.remove(path)
            removed += 1
        except OSError as exc:
            logger.warning("Could not prune %s: %s", path, exc)

    return {"removed_files": removed, "freed_bytes": freed}


@router.get("/stats/all", dependencies=[read_access])
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
