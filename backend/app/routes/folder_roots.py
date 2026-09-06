"""
Folder roots API endpoints
"""
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.db import database as db_module
from app.db.database import get_db, DB_PATH
from app.models.schemas import (
    FolderRootCreate, FolderRootResponse, FolderRootUpdate, ScanRequest, ScanResponse,
)
from app.routes.deps import require_permission
from app.services.scanner import scan_directory_detailed

logger = logging.getLogger(__name__)

router = APIRouter()

read_access = Depends(require_permission("roots.read"))
create_access = Depends(require_permission("roots.create"))
update_access = Depends(require_permission("roots.update"))
delete_access = Depends(require_permission("roots.delete"))
scan_access = Depends(require_permission("roots.scan"))

# Reading file contents into the FTS index is optional per root; cap what we
# store so one enormous script cannot bloat the index.
FTS_CONTENT_LIMIT = 100_000


def _utc_now() -> datetime:
    """Timestamps are stored as UTC everywhere; naive local time would make
    every duration and comparison wrong for non-UTC servers."""
    return datetime.now(timezone.utc)


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


def _root_from_row(row) -> dict:
    d = dict(row)
    for flag in ("recursive", "follow_symlinks", "enable_content_indexing", "enable_watch_mode"):
        if flag in d:
            d[flag] = bool(d[flag])
    return d


@router.get("/", response_model=List[FolderRootResponse], dependencies=[read_access])
async def list_folder_roots(db: aiosqlite.Connection = Depends(get_db)):
    """List all folder roots"""
    async with db.execute("SELECT * FROM folder_roots ORDER BY name") as cursor:
        rows = await cursor.fetchall()
        return [_root_from_row(row) for row in rows]


@router.get("/stats", dependencies=[read_access])
async def folder_root_stats(db: aiosqlite.Connection = Depends(get_db)):
    """
    Per-root script counts and last scan outcome.

    The UI shows these next to each root so an operator can tell at a glance
    whether a root has ever been scanned successfully.
    """
    async with db.execute(
        """
        SELECT fr.id, fr.name, fr.path, fr.last_scan_time,
               COUNT(CASE WHEN s.missing_flag = 0 THEN 1 END) AS script_count,
               COUNT(CASE WHEN s.missing_flag = 1 THEN 1 END) AS missing_count
        FROM folder_roots fr
        LEFT JOIN scripts s ON s.root_id = fr.id
        GROUP BY fr.id
        ORDER BY fr.name
        """
    ) as cursor:
        rows = await cursor.fetchall()

    stats = []
    for row in rows:
        entry = dict(row)
        async with db.execute(
            """
            SELECT status, error_message, started_at, ended_at
            FROM scan_events WHERE root_id = ?
            ORDER BY started_at DESC, id DESC LIMIT 1
            """,
            (entry["id"],),
        ) as cur:
            last = await cur.fetchone()
        entry["last_scan"] = dict(last) if last else None
        entry["path_exists"] = os.path.isdir(entry["path"])
        stats.append(entry)
    return stats


@router.post("/", response_model=FolderRootResponse, status_code=201,
             dependencies=[create_access])
async def create_folder_root(
    folder_root: FolderRootCreate,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new folder root"""
    path = folder_root.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path cannot be empty")
    if not folder_root.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if folder_root.max_file_size <= 0:
        raise HTTPException(status_code=400, detail="max_file_size must be greater than zero")

    # Store an absolute path so scans and the content-path security check agree
    # regardless of the working directory the backend was started from.
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    try:
        cursor = await db.execute(
            """
            INSERT INTO folder_roots (path, name, recursive, include_patterns,
                                     exclude_patterns, follow_symlinks, max_file_size,
                                     enable_content_indexing, enable_watch_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path,
                folder_root.name.strip(),
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

        async with db.execute(
            "SELECT * FROM folder_roots WHERE id = ?",
            (cursor.lastrowid,)
        ) as cursor:
            row = await cursor.fetchone()
            return _root_from_row(row)
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Folder root with this path already exists")


@router.get("/{root_id}", response_model=FolderRootResponse, dependencies=[read_access])
async def get_folder_root(root_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a specific folder root"""
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder root not found")
        return _root_from_row(row)


@router.put("/{root_id}", response_model=FolderRootResponse, dependencies=[update_access])
async def update_folder_root(
    root_id: int,
    data: FolderRootUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Update a folder root's settings.

    Previously the only way to change a root (for example to turn on content
    indexing or watch mode) was to delete it and rescan from scratch.
    """
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Folder root not found")

    fields, params = [], []
    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        fields.append("name = ?"); params.append(data.name.strip())
    if data.recursive is not None:
        fields.append("recursive = ?"); params.append(int(data.recursive))
    if data.include_patterns is not None:
        fields.append("include_patterns = ?"); params.append(data.include_patterns or None)
    if data.exclude_patterns is not None:
        fields.append("exclude_patterns = ?"); params.append(data.exclude_patterns or None)
    if data.follow_symlinks is not None:
        fields.append("follow_symlinks = ?"); params.append(int(data.follow_symlinks))
    if data.max_file_size is not None:
        if data.max_file_size <= 0:
            raise HTTPException(status_code=400, detail="max_file_size must be greater than zero")
        fields.append("max_file_size = ?"); params.append(data.max_file_size)
    if data.enable_content_indexing is not None:
        fields.append("enable_content_indexing = ?"); params.append(int(data.enable_content_indexing))
    if data.enable_watch_mode is not None:
        fields.append("enable_watch_mode = ?"); params.append(int(data.enable_watch_mode))

    if fields:
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(root_id)
        await db.execute(
            f"UPDATE folder_roots SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()

    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        row = await cursor.fetchone()
    return _root_from_row(row)


@router.delete("/{root_id}", dependencies=[delete_access])
async def delete_folder_root(root_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a folder root and all its scripts"""
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder root not found")

    # Stop any active watcher first so it cannot resurrect rows mid-delete.
    try:
        from app.services.watch import get_watch_manager

        manager = get_watch_manager(DB_PATH)
        if manager.is_watching(root_id):
            await manager.stop_watching(root_id)
    except Exception as exc:  # noqa: BLE001 - never block the delete
        logger.warning("Could not stop watcher for root %s: %s", root_id, exc)

    # Attachment files live on disk with no foreign key to follow, so collect
    # and unlink them before the cascade removes the rows that name them.
    from app.routes.attachments import purge_attachment_files

    async with db.execute(
        "SELECT id FROM scripts WHERE root_id = ?", (root_id,)
    ) as cursor:
        script_ids = [r[0] for r in await cursor.fetchall()]
    if script_ids:
        await purge_attachment_files(db, script_ids=script_ids)

    # scripts_fts is a virtual table with no foreign keys, so its rows must be
    # removed explicitly before the cascade drops the scripts they point at.
    await db.execute(
        "DELETE FROM scripts_fts WHERE script_id IN (SELECT id FROM scripts WHERE root_id = ?)",
        (root_id,),
    )
    await db.execute("DELETE FROM folder_roots WHERE id = ?", (root_id,))
    await db.commit()
    return {"message": "Folder root deleted successfully"}


async def _index_folders(db: aiosqlite.Connection, root_id: int, folder_paths: List[str]):
    """
    Record the directory tree for a root so the Folders API has data.

    Nothing populated this table before, so folder listings, folder notes and
    the folder tree endpoint always came back empty.
    """
    if not folder_paths:
        return

    ordered = sorted(set(folder_paths))
    for path in ordered:
        await db.execute(
            "INSERT OR IGNORE INTO folders (root_id, path) VALUES (?, ?)", (root_id, path)
        )

    # Link each folder to its parent in a second pass now that every row exists.
    async with db.execute(
        "SELECT id, path FROM folders WHERE root_id = ?", (root_id,)
    ) as cursor:
        rows = await cursor.fetchall()
    by_path = {row[1]: row[0] for row in rows}

    for path, folder_id in by_path.items():
        parent_path = os.path.dirname(path)
        parent_id = by_path.get(parent_path)
        await db.execute(
            "UPDATE folders SET parent_id = ? WHERE id = ?",
            (parent_id if parent_id != folder_id else None, folder_id),
        )

    # Drop folders that no longer exist on disk.
    known = set(ordered)
    for path, folder_id in by_path.items():
        if path not in known:
            await db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))


async def _index_script_content(db: aiosqlite.Connection, script_id: int,
                                name: str, path: str, read_content: bool):
    """Refresh a script's row in the FTS index."""
    content = ""
    if read_content:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read(FTS_CONTENT_LIMIT)
        except OSError:
            content = ""

    async with db.execute(
        "SELECT GROUP_CONCAT(content, ' ') FROM script_notes WHERE script_id = ?",
        (script_id,),
    ) as cursor:
        row = await cursor.fetchone()
    notes = row[0] if row and row[0] else ""

    await db.execute("DELETE FROM scripts_fts WHERE script_id = ?", (script_id,))
    await db.execute(
        "INSERT INTO scripts_fts (script_id, name, path, content, notes) VALUES (?, ?, ?, ?, ?)",
        (script_id, name, path, content, notes),
    )


async def _perform_scan_background(root_id: int, root_data: dict, scan_id: int,
                                   full_scan: bool = False):
    """Background task to perform the actual scanning"""
    try:
        async with db_module.connection(DB_PATH) as db:
            scripts, folders = await scan_directory_detailed(
                root_data['path'],
                root_data['recursive'],
                root_data['include_patterns'],
                root_data['exclude_patterns'],
                root_data['follow_symlinks'],
                root_data['max_file_size']
            )

            index_content = bool(root_data.get('enable_content_indexing'))
            new_count = 0
            updated_count = 0
            deleted_count = 0

            # Include the root directory itself so scripts sitting directly in
            # it are still attached to a folder row.
            await _index_folders(db, root_id, [root_data['path']] + folders)

            # Map folders by path so each script can be attached to its directory.
            async with db.execute(
                "SELECT id, path FROM folders WHERE root_id = ?", (root_id,)
            ) as cursor:
                folder_ids = {row[1]: row[0] for row in await cursor.fetchall()}

            for script in scripts:
                folder_id = folder_ids.get(os.path.dirname(script['path']))
                async with db.execute(
                    "SELECT id, hash, mtime FROM scripts WHERE path = ?",
                    (script['path'],)
                ) as cursor:
                    existing = await cursor.fetchone()

                if existing:
                    changed = (
                        existing[1] != script['hash']
                        or _normalize_mtime(existing[2]) != _normalize_mtime(script['mtime'])
                    )
                    if changed or full_scan:
                        await db.execute(
                            """
                            UPDATE scripts
                            SET root_id = ?, folder_id = ?, name = ?, extension = ?,
                                language = ?, size = ?, mtime = ?, hash = ?,
                                line_count = ?, missing_flag = 0,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (
                                root_id, folder_id,
                                script['name'], script['extension'], script['language'],
                                script['size'], script['mtime'], script['hash'],
                                script['line_count'], existing[0]
                            )
                        )
                        if changed:
                            updated_count += 1
                        if index_content:
                            await _index_script_content(
                                db, existing[0], script['name'], script['path'], True
                            )
                    else:
                        await db.execute(
                            "UPDATE scripts SET missing_flag = 0, folder_id = ? WHERE id = ?",
                            (folder_id, existing[0],)
                        )
                else:
                    cursor = await db.execute(
                        """
                        INSERT INTO scripts (root_id, folder_id, path, name, extension, language,
                                           size, mtime, hash, line_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            root_id, folder_id, script['path'], script['name'],
                            script['extension'], script['language'], script['size'],
                            script['mtime'], script['hash'], script['line_count']
                        )
                    )
                    new_count += 1
                    if index_content:
                        await _index_script_content(
                            db, cursor.lastrowid, script['name'], script['path'], True
                        )

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
                    await db.execute(
                        "DELETE FROM scripts_fts WHERE script_id = ?", (row[0],)
                    )
                    deleted_count += 1

            ended_at = _utc_now()
            await db.execute(
                """
                UPDATE scan_events
                SET ended_at = ?, status = 'completed',
                    new_count = ?, updated_count = ?, deleted_count = ?
                WHERE id = ?
                """,
                (ended_at.isoformat(), new_count, updated_count, deleted_count, scan_id)
            )
            await db.execute(
                "UPDATE folder_roots SET last_scan_time = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (ended_at.isoformat(), root_id)
            )
            await db.commit()

    except Exception as exc:  # noqa: BLE001 - the failure belongs in the scan event
        logger.exception("Scan %s for root %s failed", scan_id, root_id)
        try:
            async with db_module.connection(DB_PATH) as db:
                await db.execute(
                    """
                    UPDATE scan_events
                    SET ended_at = ?, status = 'failed', error_count = 1, error_message = ?
                    WHERE id = ?
                    """,
                    (_utc_now().isoformat(), str(exc), scan_id)
                )
                await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Could not record scan failure for scan %s", scan_id)


@router.post("/{root_id}/scan", response_model=ScanResponse, status_code=202,
             dependencies=[scan_access])
async def scan_folder_root(
    root_id: int,
    scan_request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Scan a folder root for scripts (returns immediately, runs in background)"""
    async with db.execute("SELECT * FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        root_row = await cursor.fetchone()
        if not root_row:
            raise HTTPException(status_code=404, detail="Folder root not found")
        root = _root_from_row(root_row)

    if not os.path.isdir(root["path"]):
        raise HTTPException(
            status_code=400,
            detail=f"Path is no longer accessible: {root['path']}",
        )

    # Refuse to queue a second scan of the same root; two concurrent walks
    # would fight over the same rows and double-count the results.
    async with db.execute(
        "SELECT id FROM scan_events WHERE root_id = ? AND status = 'running'", (root_id,)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=409, detail="A scan is already running for this root")

    started_at = _utc_now()
    cursor = await db.execute(
        """
        INSERT INTO scan_events (root_id, started_at, status)
        VALUES (?, ?, 'running')
        """,
        (root_id, started_at.isoformat())
    )
    scan_id = cursor.lastrowid
    await db.commit()

    background_tasks.add_task(
        _perform_scan_background, root_id, root, scan_id, scan_request.full_scan
    )

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


@router.get("/{root_id}/scans", dependencies=[read_access])
async def list_scans(
    root_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Recent scan history for a root."""
    async with db.execute("SELECT id FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Folder root not found")
    async with db.execute(
        "SELECT * FROM scan_events WHERE root_id = ? ORDER BY started_at DESC, id DESC LIMIT ?",
        (root_id, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/{root_id}/scan/{scan_id}", dependencies=[read_access])
async def get_scan_status(
    root_id: int,
    scan_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Get the status of a scan operation"""
    async with db.execute("SELECT id FROM folder_roots WHERE id = ?", (root_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Folder root not found")

    async with db.execute(
        "SELECT id, status, new_count, updated_count, deleted_count, error_count, "
        "error_message, started_at, ended_at FROM scan_events WHERE id = ? AND root_id = ?",
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
        'error_count': row[5] or 0,
        'error_message': row[6],
        'started_at': row[7],
        'ended_at': row[8]
    }
