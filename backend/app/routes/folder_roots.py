"""
Folder roots API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List
from datetime import datetime
import aiosqlite

from app.db.database import get_db, DB_PATH
from app.models.schemas import FolderRootCreate, FolderRootResponse, ScanRequest, ScanResponse
from app.services.scanner import scan_directory

router = APIRouter()


def _normalize_mtime(value):
    """Normalize SQLite/Python datetime values for consistent comparisons."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=' ')
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.replace(microsecond=0).isoformat(sep=' ')
        except ValueError:
            return value
    return str(value)

@router.get("/", response_model=List[FolderRootResponse])
async def list_folder_roots(db: aiosqlite.Connection = Depends(get_db)):
    """List all folder roots"""
    async with db.execute("SELECT * FROM folder_roots ORDER BY name") as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

@router.post("/", response_model=FolderRootResponse)
async def create_folder_root(
    folder_root: FolderRootCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new folder root"""
    try:
        cursor = await db.execute(
            """
            INSERT INTO folder_roots (path, name, recursive, include_patterns, 
                                     exclude_patterns, follow_symlinks, max_file_size, 
                                     enable_content_indexing, enable_watch_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder_root.path,
                folder_root.name,
                folder_root.recursive,
                folder_root.include_patterns,
                folder_root.exclude_patterns,
                folder_root.follow_symlinks,
                folder_root.max_file_size,
                folder_root.enable_content_indexing,
                folder_root.enable_watch_mode
            )
        )
        await db.commit()
        
        # Fetch the created folder root
        async with db.execute(
            "SELECT * FROM folder_roots WHERE id = ?",
            (cursor.lastrowid,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row)
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Folder root with this path already exists")

@router.get("/{root_id}", response_model=FolderRootResponse)
async def get_folder_root(root_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a specific folder root"""
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder root not found")
        return dict(row)

@router.delete("/{root_id}")
async def delete_folder_root(root_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a folder root and all its scripts"""
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder root not found")
    
    await db.execute("DELETE FROM folder_roots WHERE id = ?", (root_id,))
    await db.commit()
    return {"message": "Folder root deleted successfully"}

async def _perform_scan_background(root_id: int, root_data: dict, scan_id: int):
    """Background task to perform the actual scanning"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Scan directory
            scripts = await scan_directory(
                root_data['path'],
                root_data['recursive'],
                root_data['include_patterns'],
                root_data['exclude_patterns'],
                root_data['follow_symlinks'],
                root_data['max_file_size']
            )
            
            new_count = 0
            updated_count = 0
            deleted_count = 0
            
            # Process scanned scripts
            for script in scripts:
                # Check if script already exists
                async with db.execute(
                    "SELECT id, hash, mtime FROM scripts WHERE path = ?",
                    (script['path'],)
                ) as cursor:
                    existing = await cursor.fetchone()
                
                if existing:
                    # Update if changed
                    if (
                        existing[1] != script['hash']
                        or _normalize_mtime(existing[2]) != _normalize_mtime(script['mtime'])
                    ):
                        await db.execute(
                            """
                            UPDATE scripts 
                            SET name = ?, extension = ?, language = ?, size = ?,
                                mtime = ?, hash = ?, line_count = ?, missing_flag = 0,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (
                                script['name'], script['extension'], script['language'],
                                script['size'], script['mtime'], script['hash'],
                                script['line_count'], existing[0]
                            )
                        )
                        updated_count += 1
                    else:
                        # Mark as not missing
                        await db.execute(
                            "UPDATE scripts SET missing_flag = 0 WHERE id = ?",
                            (existing[0],)
                        )
                else:
                    # Insert new script
                    await db.execute(
                        """
                        INSERT INTO scripts (root_id, path, name, extension, language,
                                           size, mtime, hash, line_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            root_id, script['path'], script['name'], script['extension'],
                            script['language'], script['size'], script['mtime'],
                            script['hash'], script['line_count']
                        )
                    )
                    new_count += 1
            
            # Mark missing scripts
            scanned_paths = {s['path'] for s in scripts}
            async with db.execute(
                "SELECT id, path FROM scripts WHERE root_id = ? AND missing_flag = 0",
                (root_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    if row[1] not in scanned_paths:
                        await db.execute(
                            "UPDATE scripts SET missing_flag = 1 WHERE id = ?",
                            (row[0],)
                        )
                        deleted_count += 1
            
            # Update scan event with success
            ended_at = datetime.now()
            await db.execute(
                """
                UPDATE scan_events
                SET ended_at = ?, status = 'completed',
                    new_count = ?, updated_count = ?, deleted_count = ?
                WHERE id = ?
                """,
                (ended_at, new_count, updated_count, deleted_count, scan_id)
            )
            
            # Update folder root scan time
            await db.execute(
                "UPDATE folder_roots SET last_scan_time = ? WHERE id = ?",
                (ended_at, root_id)
            )
            
            await db.commit()
    
    except Exception as e:
        # Update scan event with error
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                UPDATE scan_events
                SET ended_at = ?, status = 'failed', error_message = ?
                WHERE id = ?
                """,
                (datetime.now(), str(e), scan_id)
            )
            await db.commit()

@router.post("/{root_id}/scan", response_model=ScanResponse)
async def scan_folder_root(
    root_id: int,
    scan_request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Scan a folder root for scripts (returns immediately, runs in background)"""
    # Get folder root details
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        root_row = await cursor.fetchone()
        if not root_row:
            raise HTTPException(status_code=404, detail="Folder root not found")
        root = dict(root_row)
    
    # Create scan event
    started_at = datetime.now()
    cursor = await db.execute(
        """
        INSERT INTO scan_events (root_id, started_at, status)
        VALUES (?, ?, 'running')
        """,
        (root_id, started_at)
    )
    scan_id = cursor.lastrowid
    await db.commit()
    
    # Schedule scan as background task
    background_tasks.add_task(_perform_scan_background, root_id, root, scan_id)
    
    # Return immediately with scan ID
    return {
        'scan_id': scan_id,
        'status': 'running',
        'new_count': 0,
        'updated_count': 0,
        'deleted_count': 0,
        'error_count': 0,
        'started_at': started_at,
        'ended_at': None
    }

@router.get("/{root_id}/scan/{scan_id}")
async def get_scan_status(
    root_id: int,
    scan_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Get the status of a scan operation"""
    # Verify root exists
    async with db.execute("SELECT id FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Folder root not found")
    
    # Get scan event
    async with db.execute(
        "SELECT id, status, new_count, updated_count, deleted_count, error_message, started_at, ended_at FROM scan_events WHERE id = ? AND root_id = ?",
        (scan_id, root_id)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scan not found")
    
    return {
        'scan_id': row[0],
        'status': row[1],
        'new_count': row[2] or 0,
        'updated_count': row[3] or 0,
        'deleted_count': row[4] or 0,
        'error_message': row[5],
        'started_at': row[6],
        'ended_at': row[7]
    }
