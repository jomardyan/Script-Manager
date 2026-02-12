"""
Database configuration and initialization
"""
import os
import aiosqlite
from pathlib import Path

# Database configuration
DB_PATH = os.getenv("DATABASE_PATH", "./data/scripts.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

async def get_db():
    """Get database connection"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    """Initialize database with schema"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")
        
        # Create folder_roots table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS folder_roots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                recursive BOOLEAN DEFAULT 1,
                include_patterns TEXT,
                exclude_patterns TEXT,
                follow_symlinks BOOLEAN DEFAULT 0,
                max_file_size INTEGER DEFAULT 10485760,
                enable_content_indexing BOOLEAN DEFAULT 0,
                enable_watch_mode BOOLEAN DEFAULT 0,
                last_scan_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create folders table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_id INTEGER NOT NULL,
                path TEXT NOT NULL UNIQUE,
                parent_id INTEGER,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (root_id) REFERENCES folder_roots(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES folders(id) ON DELETE CASCADE
            )
        """)
        
        # Create scripts table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_id INTEGER NOT NULL,
                folder_id INTEGER,
                path TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                extension TEXT,
                language TEXT,
                size INTEGER,
                mtime TIMESTAMP,
                hash TEXT,
                line_count INTEGER,
                missing_flag BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (root_id) REFERENCES folder_roots(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
            )
        """)
        
        # Create script_notes table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS script_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                is_markdown BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
            )
        """)
        
        # Create tags table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                group_name TEXT,
                color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create script_tags table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS script_tags (
                script_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (script_id, tag_id),
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)
        
        # Create script_fields table for custom metadata
        await db.execute("""
            CREATE TABLE IF NOT EXISTS script_fields (
                script_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (script_id, key),
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
            )
        """)
        
        # Create script_status table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS script_status (
                script_id INTEGER PRIMARY KEY,
                status TEXT DEFAULT 'active',
                classification TEXT,
                owner TEXT,
                environment TEXT,
                deprecated_date TIMESTAMP,
                migration_note TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
            )
        """)
        
        # Create scan_events table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scan_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_id INTEGER NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                status TEXT NOT NULL,
                new_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                deleted_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (root_id) REFERENCES folder_roots(id) ON DELETE CASCADE
            )
        """)
        
        # Create change_log table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER NOT NULL,
                event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                change_type TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                actor TEXT,
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
            )
        """)
        
        # Create attachments table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER,
                note_id INTEGER,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE,
                FOREIGN KEY (note_id) REFERENCES script_notes(id) ON DELETE CASCADE
            )
        """)
        
        # Create users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT,
                hashed_password TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                is_superuser BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create roles table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                permissions TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create user_roles junction table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
            )
        """)
        
        # Create saved_searches table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saved_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                query_params TEXT NOT NULL,
                is_pinned BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create FTS5 virtual table for full-text search
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS scripts_fts USING fts5(
                script_id UNINDEXED,
                name,
                path,
                content,
                notes,
                tokenize='porter unicode61'
            )
        """)
        
        # Create indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_name ON scripts(name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_extension ON scripts(extension)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_language ON scripts(language)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_hash ON scripts(hash)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_mtime ON scripts(mtime)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_script_tags_script ON script_tags(script_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_script_tags_tag ON script_tags(tag_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_change_log_script ON change_log(script_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_change_log_time ON change_log(event_time)")
        
        await db.commit()
        print("Database initialized successfully")
