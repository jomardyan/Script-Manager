"""
Watch Mode service for automatic filesystem monitoring.

A watchdog observer reports filesystem events from its own thread. Those
events are handed to a single long-lived worker thread per folder root, which
owns one SQLite connection and drains a queue.

The previous design started a brand new thread and a brand new event loop and
connection for every individual event, so saving a directory of files could
spawn hundreds of concurrent writers against one SQLite file, each without a
busy timeout. It also ignored the folder root's include and exclude patterns,
so watch mode indexed files a scan would have skipped.
"""
import logging
import queue
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.services.scanner import (
    detect_language, get_file_hash, get_line_count, is_script_file, match_patterns,
)

logger = logging.getLogger(__name__)

# Sentinel that tells a worker to finish.
_STOP = object()

# Bound the backlog so a runaway process writing thousands of files cannot grow
# the queue without limit; excess events are dropped and logged, and the next
# manual scan reconciles whatever was missed.
MAX_QUEUE_SIZE = 10_000


class ScriptFileHandler(FileSystemEventHandler):
    """Translates watchdog events into work items for the root's worker."""

    def __init__(self, root_id: int, root_path: str, work_queue: "queue.Queue",
                 include_patterns: Optional[str], exclude_patterns: Optional[str]):
        self.root_id = root_id
        self.root_path = root_path
        self.queue = work_queue
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns

    # ── Filtering ────────────────────────────────────────────────────────────

    def _tracked(self, path: str) -> bool:
        """Apply the same filters the scanner uses, so both agree on what is indexed."""
        if not is_script_file(path):
            return False
        if self.exclude_patterns and match_patterns(path, self.exclude_patterns):
            return False
        if self.include_patterns and not match_patterns(path, self.include_patterns):
            return False
        return True

    def _submit(self, action: str, path: str):
        try:
            self.queue.put_nowait((action, path))
        except queue.Full:
            logger.warning(
                "Watch queue for root %s is full; dropping %s event for %s",
                self.root_id, action, path,
            )

    # ── Events ───────────────────────────────────────────────────────────────

    def on_created(self, event):
        if event.is_directory:
            return
        if self._tracked(event.src_path):
            self._submit("upsert", event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        if self._tracked(event.src_path):
            self._submit("upsert", event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        if self._tracked(event.src_path):
            self._submit("missing", event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._tracked(event.src_path):
            self._submit("missing", event.src_path)
        if self._tracked(event.dest_path):
            self._submit("upsert", event.dest_path)


class _RootWorker(threading.Thread):
    """One worker thread per watched root, owning a single SQLite connection."""

    def __init__(self, root_id: int, db_path: str, work_queue: "queue.Queue",
                 max_file_size: int):
        super().__init__(daemon=True, name=f"watch-root-{root_id}")
        self.root_id = root_id
        self.db_path = db_path
        self.queue = work_queue
        self.max_file_size = max_file_size

    def run(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
            while True:
                item = self.queue.get()
                if item is _STOP:
                    return
                action, path = item
                try:
                    if action == "upsert":
                        self._upsert(conn, path)
                    elif action == "missing":
                        self._mark_missing(conn, path)
                except sqlite3.Error as exc:
                    logger.warning("Watch: database error handling %s for %s: %s",
                                   action, path, exc)
                except OSError as exc:
                    logger.warning("Watch: filesystem error handling %s for %s: %s",
                                   action, path, exc)
                finally:
                    self.queue.task_done()
        finally:
            conn.close()

    # ── Database work ────────────────────────────────────────────────────────

    def _upsert(self, conn: sqlite3.Connection, file_path: str):
        path_obj = Path(file_path)
        if not path_obj.is_file():
            return
        stat = path_obj.stat()
        if stat.st_size > self.max_file_size:
            return

        absolute = str(path_obj.absolute())
        # Stored in UTC to match every other timestamp in the database; a naive
        # local value made date filters wrong on non-UTC servers.
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        row = conn.execute(
            "SELECT id FROM scripts WHERE path = ?", (absolute,)
        ).fetchone()

        values = (
            path_obj.name, path_obj.suffix.lower(), detect_language(file_path),
            stat.st_size, mtime, get_file_hash(file_path), get_line_count(file_path),
        )

        if row:
            conn.execute(
                """
                UPDATE scripts
                SET name = ?, extension = ?, language = ?, size = ?,
                    mtime = ?, hash = ?, line_count = ?, missing_flag = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE path = ?
                """,
                values + (absolute,),
            )
            script_id = row[0]
        else:
            cursor = conn.execute(
                """
                INSERT INTO scripts (root_id, path, name, extension, language,
                                     size, mtime, hash, line_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (self.root_id, absolute) + values,
            )
            script_id = cursor.lastrowid

        self._reindex(conn, script_id, absolute, path_obj.name)
        conn.commit()
        logger.debug("Watch: indexed %s", absolute)

    def _reindex(self, conn: sqlite3.Connection, script_id: int, path: str, name: str):
        """
        Keep the full-text index in step with the file.

        Without this, watch mode silently left FTS results pointing at stale
        content until somebody triggered a manual rebuild.
        """
        indexing = conn.execute(
            "SELECT enable_content_indexing FROM folder_roots WHERE id = ?",
            (self.root_id,),
        ).fetchone()
        content = ""
        if indexing and indexing[0]:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read(100_000)
            except OSError:
                content = ""

        notes_row = conn.execute(
            "SELECT GROUP_CONCAT(content, ' ') FROM script_notes WHERE script_id = ?",
            (script_id,),
        ).fetchone()
        notes = notes_row[0] if notes_row and notes_row[0] else ""

        conn.execute("DELETE FROM scripts_fts WHERE script_id = ?", (script_id,))
        conn.execute(
            "INSERT INTO scripts_fts (script_id, name, path, content, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (script_id, name, path, content, notes),
        )

    def _mark_missing(self, conn: sqlite3.Connection, file_path: str):
        absolute = str(Path(file_path).absolute())
        conn.execute(
            "UPDATE scripts SET missing_flag = 1, updated_at = CURRENT_TIMESTAMP "
            "WHERE path = ?",
            (absolute,),
        )
        conn.execute(
            "DELETE FROM scripts_fts WHERE script_id IN "
            "(SELECT id FROM scripts WHERE path = ?)",
            (absolute,),
        )
        conn.commit()
        logger.debug("Watch: marked missing %s", absolute)


class WatchManager:
    """Manages filesystem watchers for folder roots"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.observers: Dict[int, Tuple[Observer, _RootWorker, "queue.Queue"]] = {}

    async def start_watching(self, root_id: int, root_path: str, recursive: bool,
                             include_patterns: Optional[str],
                             exclude_patterns: Optional[str],
                             max_file_size: int):
        """Start watching a folder root"""
        await self.stop_watching(root_id)

        work_queue: "queue.Queue" = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        worker = _RootWorker(root_id, self.db_path, work_queue, max_file_size)
        worker.start()

        handler = ScriptFileHandler(
            root_id, root_path, work_queue, include_patterns, exclude_patterns
        )
        observer = Observer()
        observer.schedule(handler, root_path, recursive=bool(recursive))
        observer.start()

        self.observers[root_id] = (observer, worker, work_queue)
        logger.info("Started watching folder root %s: %s", root_id, root_path)

    async def stop_watching(self, root_id: int):
        """Stop watching a folder root"""
        entry = self.observers.pop(root_id, None)
        if not entry:
            return
        observer, worker, work_queue = entry
        observer.stop()
        observer.join(timeout=2)
        work_queue.put(_STOP)
        worker.join(timeout=5)
        logger.info("Stopped watching folder root %s", root_id)

    async def stop_all(self):
        """Stop all watchers"""
        for root_id in list(self.observers.keys()):
            await self.stop_watching(root_id)

    def is_watching(self, root_id: int) -> bool:
        """Check if a folder root is being watched"""
        return root_id in self.observers

    def get_watching_roots(self) -> list:
        """Get list of root IDs currently being watched"""
        return list(self.observers.keys())

    def pending_events(self, root_id: int) -> int:
        """How many filesystem events are still queued for a root."""
        entry = self.observers.get(root_id)
        return entry[2].qsize() if entry else 0


# Global watch manager instance
watch_manager: Optional[WatchManager] = None


def get_watch_manager(db_path: str) -> WatchManager:
    """Get or create the global watch manager"""
    global watch_manager
    if watch_manager is None:
        watch_manager = WatchManager(db_path)
    else:
        # The test suite and the CLI point DB_PATH at different databases; keep
        # the singleton aimed at whichever one the caller is using.
        watch_manager.db_path = db_path
    return watch_manager
