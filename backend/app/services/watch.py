"""
Watch Mode service for automatic filesystem monitoring
"""
import asyncio
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Dict
import aiosqlite
from datetime import datetime

from app.services.scanner import is_script_file, get_file_hash, get_line_count, detect_language


class ScriptFileHandler(FileSystemEventHandler):
    """Handler for script file changes"""
    
    def __init__(self, root_id: int, root_path: str, db_path: str, recursive: bool, 
                 include_patterns: str, exclude_patterns: str, max_file_size: int):
        self.root_id = root_id
        self.root_path = root_path
        self.db_path = db_path
        self.recursive = recursive
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.max_file_size = max_file_size
        self.pending_changes = []
    
    def on_created(self, event):
        """Handle file creation"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if is_script_file(file_path):
            print(f"Watch: File created: {file_path}")
            self._schedule_file_update(file_path, 'created')
    
    def on_modified(self, event):
        """Handle file modification"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if is_script_file(file_path):
            print(f"Watch: File modified: {file_path}")
            self._schedule_file_update(file_path, 'modified')
    
    def on_deleted(self, event):
        """Handle file deletion"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if is_script_file(file_path):
            print(f"Watch: File deleted: {file_path}")
            self._schedule_file_deletion(file_path)
    
    def on_moved(self, event):
        """Handle file move/rename"""
        if event.is_directory:
            return
        
        old_path = event.src_path
        new_path = event.dest_path
        
        if is_script_file(old_path) or is_script_file(new_path):
            print(f"Watch: File moved: {old_path} -> {new_path}")
            # Treat as delete + create
            if is_script_file(old_path):
                self._schedule_file_deletion(old_path)
            if is_script_file(new_path):
                self._schedule_file_update(new_path, 'created')
    
    def _schedule_file_update(self, file_path: str, change_type: str):
        """Schedule a file to be updated in the database"""
        # Run database operation in a separate thread since watchdog runs in its own thread
        import threading
        thread = threading.Thread(target=self._sync_update_file, args=(file_path, change_type))
        thread.daemon = True
        thread.start()
    
    def _schedule_file_deletion(self, file_path: str):
        """Schedule a file to be marked as missing"""
        import threading
        thread = threading.Thread(target=self._sync_mark_file_missing, args=(file_path,))
        thread.daemon = True
        thread.start()
    
    def _sync_update_file(self, file_path: str, change_type: str):
        """Synchronous wrapper for file update"""
        import asyncio
        asyncio.run(self._update_file(file_path, change_type))
    
    def _sync_mark_file_missing(self, file_path: str):
        """Synchronous wrapper for marking file missing"""
        import asyncio
        asyncio.run(self._mark_file_missing(file_path))
    
    async def _update_file(self, file_path: str, change_type: str):
        """Update file in database"""
        try:
            # Get file metadata
            path_obj = Path(file_path)
            stat = path_obj.stat()
            
            # Check file size
            if stat.st_size > self.max_file_size:
                return
            
            metadata = {
                'path': str(path_obj.absolute()),
                'name': path_obj.name,
                'extension': path_obj.suffix.lower(),
                'language': detect_language(file_path),
                'size': stat.st_size,
                'mtime': datetime.fromtimestamp(stat.st_mtime),
                'hash': get_file_hash(file_path),
                'line_count': get_line_count(file_path)
            }
            
            # Update database
            async with aiosqlite.connect(self.db_path) as db:
                # Check if script exists
                async with db.execute(
                    "SELECT id FROM scripts WHERE path = ?",
                    (metadata['path'],)
                ) as cursor:
                    existing = await cursor.fetchone()
                
                if existing:
                    # Update existing script
                    await db.execute(
                        """
                        UPDATE scripts 
                        SET name = ?, extension = ?, language = ?, size = ?,
                            mtime = ?, hash = ?, line_count = ?, missing_flag = 0,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE path = ?
                        """,
                        (
                            metadata['name'], metadata['extension'], metadata['language'],
                            metadata['size'], metadata['mtime'], metadata['hash'],
                            metadata['line_count'], metadata['path']
                        )
                    )
                    print(f"Watch: Updated script in DB: {file_path}")
                else:
                    # Insert new script
                    await db.execute(
                        """
                        INSERT INTO scripts (root_id, path, name, extension, language,
                                           size, mtime, hash, line_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.root_id, metadata['path'], metadata['name'],
                            metadata['extension'], metadata['language'], metadata['size'],
                            metadata['mtime'], metadata['hash'], metadata['line_count']
                        )
                    )
                    print(f"Watch: Inserted new script in DB: {file_path}")
                
                await db.commit()
        
        except Exception as e:
            print(f"Watch: Error updating file {file_path}: {e}")
    
    async def _mark_file_missing(self, file_path: str):
        """Mark file as missing in database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE scripts SET missing_flag = 1 WHERE path = ?",
                    (file_path,)
                )
                await db.commit()
                print(f"Watch: Marked file as missing: {file_path}")
        except Exception as e:
            print(f"Watch: Error marking file missing {file_path}: {e}")


class WatchManager:
    """Manages filesystem watchers for folder roots"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.observers: Dict[int, Observer] = {}
    
    async def start_watching(self, root_id: int, root_path: str, recursive: bool,
                           include_patterns: str, exclude_patterns: str, max_file_size: int):
        """Start watching a folder root"""
        # Stop existing watcher if any
        await self.stop_watching(root_id)
        
        # Create handler
        handler = ScriptFileHandler(
            root_id, root_path, self.db_path, recursive,
            include_patterns, exclude_patterns, max_file_size
        )
        
        # Create observer
        observer = Observer()
        observer.schedule(handler, root_path, recursive=recursive)
        observer.start()
        
        self.observers[root_id] = observer
        print(f"Started watching folder root {root_id}: {root_path}")
    
    async def stop_watching(self, root_id: int):
        """Stop watching a folder root"""
        if root_id in self.observers:
            observer = self.observers[root_id]
            observer.stop()
            observer.join(timeout=2)
            del self.observers[root_id]
            print(f"Stopped watching folder root {root_id}")
    
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


# Global watch manager instance
watch_manager = None


def get_watch_manager(db_path: str) -> WatchManager:
    """Get or create the global watch manager"""
    global watch_manager
    if watch_manager is None:
        watch_manager = WatchManager(db_path)
    return watch_manager
