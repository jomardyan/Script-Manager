"""
Watch Mode API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
import os

from app.db.database import get_db, DB_PATH
from app.services.watch import get_watch_manager

router = APIRouter()


@router.post("/start/{root_id}")
async def start_watch_mode(
    root_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Start watching a folder root for filesystem changes"""
    # Get folder root details
    async with db.execute(
        "SELECT path, recursive, include_patterns, exclude_patterns, max_file_size, enable_watch_mode FROM folder_roots WHERE id = ?",
        (root_id,)
    ) as cursor:
        root = await cursor.fetchone()
        if not root:
            raise HTTPException(status_code=404, detail="Folder root not found")
    
    path, recursive, include_patterns, exclude_patterns, max_file_size, enable_watch_mode = root
    
    # Check if watch mode is enabled for this root
    if not enable_watch_mode:
        raise HTTPException(
            status_code=400,
            detail="Watch mode is not enabled for this folder root. Update enable_watch_mode to true first."
        )
    
    # Check if path exists
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    
    # Start watching
    watch_manager = get_watch_manager(DB_PATH)
    
    if watch_manager.is_watching(root_id):
        return {
            "message": "Folder root is already being watched",
            "root_id": root_id,
            "path": path
        }
    
    await watch_manager.start_watching(
        root_id, path, recursive,
        include_patterns, exclude_patterns, max_file_size
    )
    
    return {
        "message": "Watch mode started successfully",
        "root_id": root_id,
        "path": path,
        "recursive": recursive
    }


@router.post("/stop/{root_id}")
async def stop_watch_mode(
    root_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Stop watching a folder root"""
    # Verify root exists
    async with db.execute(
        "SELECT path FROM folder_roots WHERE id = ?",
        (root_id,)
    ) as cursor:
        root = await cursor.fetchone()
        if not root:
            raise HTTPException(status_code=404, detail="Folder root not found")
    
    watch_manager = get_watch_manager(DB_PATH)
    
    if not watch_manager.is_watching(root_id):
        return {
            "message": "Folder root is not being watched",
            "root_id": root_id
        }
    
    await watch_manager.stop_watching(root_id)
    
    return {
        "message": "Watch mode stopped successfully",
        "root_id": root_id
    }


@router.get("/status")
async def watch_status(db: aiosqlite.Connection = Depends(get_db)):
    """Get watch mode status for all folder roots"""
    watch_manager = get_watch_manager(DB_PATH)
    watching_roots = watch_manager.get_watching_roots()
    
    # Get details of watched roots
    if watching_roots:
        placeholders = ','.join('?' * len(watching_roots))
        query = f"SELECT id, name, path, enable_watch_mode FROM folder_roots WHERE id IN ({placeholders})"
        async with db.execute(query, watching_roots) as cursor:
            roots = await cursor.fetchall()
            watched = [
                {
                    "root_id": r[0],
                    "name": r[1],
                    "path": r[2],
                    "enabled": bool(r[3]),
                    "watching": True
                }
                for r in roots
            ]
    else:
        watched = []
    
    # Get roots with watch mode enabled but not watching
    async with db.execute(
        "SELECT id, name, path FROM folder_roots WHERE enable_watch_mode = 1"
    ) as cursor:
        roots = await cursor.fetchall()
        enabled = [
            {
                "root_id": r[0],
                "name": r[1],
                "path": r[2],
                "enabled": True,
                "watching": r[0] in watching_roots
            }
            for r in roots
        ]
    
    return {
        "watching_count": len(watching_roots),
        "watching_roots": watching_roots,
        "enabled_roots": enabled,
        "watched_details": watched
    }


@router.post("/start-all")
async def start_all_watch_mode(db: aiosqlite.Connection = Depends(get_db)):
    """Start watch mode for all folder roots that have it enabled"""
    watch_manager = get_watch_manager(DB_PATH)
    
    # Get all roots with watch mode enabled
    async with db.execute(
        "SELECT id, path, recursive, include_patterns, exclude_patterns, max_file_size FROM folder_roots WHERE enable_watch_mode = 1"
    ) as cursor:
        roots = await cursor.fetchall()
    
    started = []
    errors = []
    
    for root in roots:
        root_id, path, recursive, include_patterns, exclude_patterns, max_file_size = root
        
        try:
            if not watch_manager.is_watching(root_id):
                await watch_manager.start_watching(
                    root_id, path, recursive,
                    include_patterns, exclude_patterns, max_file_size
                )
                started.append(root_id)
        except Exception as e:
            errors.append({"root_id": root_id, "error": str(e)})
    
    return {
        "message": f"Started watch mode for {len(started)} folder roots",
        "started": started,
        "errors": errors
    }


@router.post("/stop-all")
async def stop_all_watch_mode():
    """Stop watch mode for all folder roots"""
    watch_manager = get_watch_manager(DB_PATH)
    watching = watch_manager.get_watching_roots()
    
    await watch_manager.stop_all()
    
    return {
        "message": f"Stopped watch mode for {len(watching)} folder roots",
        "stopped": watching
    }
