"""
Database configuration and initialization
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

# Database configuration
DB_PATH = os.getenv("DATABASE_PATH", "./data/scripts.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# Applied to every connection the application opens. Without foreign_keys the
# ON DELETE CASCADE clauses in the schema silently do nothing, which orphans
# scripts, notes, tags, pings and executions whenever a parent row is deleted.
CONNECTION_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
)


async def apply_connection_pragmas(db: aiosqlite.Connection):
    """Apply the per-connection pragmas every code path relies on."""
    for pragma in CONNECTION_PRAGMAS:
        await db.execute(pragma)


@asynccontextmanager
async def connection(db_path: str = None):
    """
    Open a configured connection for the duration of the block.

    An async context manager rather than a coroutine returning a connection:
    aiosqlite's Connection is both awaitable and a context manager, so
    `async with await connect()` starts its worker thread twice and deadlocks.
    """
    async with aiosqlite.connect(db_path or DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await apply_connection_pragmas(db)
        yield db


async def get_db():
    """Get database connection (FastAPI dependency)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await apply_connection_pragmas(db)
        yield db


async def _ensure_column(db, table: str, column: str, ddl: str):
    """
    Add a column to an existing table if it is missing.

    `CREATE TABLE IF NOT EXISTS` never alters an existing table, so databases
    created by an older release would otherwise never receive new columns.
    """
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        existing = {row[1] for row in await cursor.fetchall()}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


async def _run_migrations(db):
    """Apply additive schema migrations to databases created by older versions."""
    await _ensure_column(db, "folder_roots", "enable_content_indexing", "BOOLEAN DEFAULT 0")
    await _ensure_column(db, "folder_roots", "enable_watch_mode", "BOOLEAN DEFAULT 0")
    await _ensure_column(db, "schedule_jobs", "next_run_at", "TIMESTAMP")
    await _ensure_column(db, "schedule_jobs", "notify_channel_ids", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "monitors", "notify_channel_ids", "TEXT DEFAULT '[]'")
    await _ensure_column(db, "incidents", "acknowledged_by", "TEXT")
    await _ensure_column(db, "users", "last_login_at", "TIMESTAMP")


async def cleanup_orphans(db) -> dict:
    """
    Remove rows orphaned by deletes that ran while foreign_keys was OFF.

    Earlier releases opened request connections without `PRAGMA foreign_keys`,
    so deleting a folder root (or script, monitor, job) left its children
    behind. New installs are unaffected; this is a one-shot repair for
    existing databases.
    """
    statements = {
        "folders": "DELETE FROM folders WHERE root_id NOT IN (SELECT id FROM folder_roots)",
        "scripts": "DELETE FROM scripts WHERE root_id NOT IN (SELECT id FROM folder_roots)",
        "script_notes": "DELETE FROM script_notes WHERE script_id NOT IN (SELECT id FROM scripts)",
        "script_tags": (
            "DELETE FROM script_tags WHERE script_id NOT IN (SELECT id FROM scripts) "
            "OR tag_id NOT IN (SELECT id FROM tags)"
        ),
        "script_status": "DELETE FROM script_status WHERE script_id NOT IN (SELECT id FROM scripts)",
        "script_fields": "DELETE FROM script_fields WHERE script_id NOT IN (SELECT id FROM scripts)",
        "change_log": "DELETE FROM change_log WHERE script_id NOT IN (SELECT id FROM scripts)",
        "scan_events": "DELETE FROM scan_events WHERE root_id NOT IN (SELECT id FROM folder_roots)",
        "attachments": (
            "DELETE FROM attachments WHERE (script_id IS NOT NULL AND script_id NOT IN (SELECT id FROM scripts)) "
            "OR (note_id IS NOT NULL AND note_id NOT IN (SELECT id FROM script_notes))"
        ),
        "monitor_pings": "DELETE FROM monitor_pings WHERE monitor_id NOT IN (SELECT id FROM monitors)",
        "job_executions": "DELETE FROM job_executions WHERE job_id NOT IN (SELECT id FROM schedule_jobs)",
        "user_roles": (
            "DELETE FROM user_roles WHERE user_id NOT IN (SELECT id FROM users) "
            "OR role_id NOT IN (SELECT id FROM roles)"
        ),
        "scripts_fts": "DELETE FROM scripts_fts WHERE script_id NOT IN (SELECT id FROM scripts)",
    }
    removed = {}
    for table, sql in statements.items():
        cursor = await db.execute(sql)
        if cursor.rowcount and cursor.rowcount > 0:
            removed[table] = cursor.rowcount
    await db.commit()
    return removed


async def init_db():
    """Initialize database with schema"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys
        await apply_connection_pragmas(db)
        # Write-Ahead Logging keeps readers from blocking the writer, which
        # matters because scans, the scheduler and requests all write.
        try:
            await db.execute("PRAGMA journal_mode = WAL")
        except aiosqlite.Error:
            # Not supported on some filesystems (e.g. certain network mounts).
            pass

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
                last_login_at TIMESTAMP,
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

        # Create app_settings table for wizard/configuration state
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create monitors table for heartbeat/fail-safe monitoring
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                expected_interval_seconds INTEGER NOT NULL DEFAULT 300,
                grace_period_seconds INTEGER NOT NULL DEFAULT 60,
                ping_key TEXT NOT NULL UNIQUE,
                last_ping_at TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'new',
                notify_channel_ids TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create monitor_pings table for ping history
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitor_pings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id INTEGER NOT NULL,
                pinged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_ip TEXT,
                FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
            )
        """)

        # Create schedule_jobs table for cron/scheduled tasks
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                script_id INTEGER,
                command TEXT,
                cron_expression TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                enabled BOOLEAN NOT NULL DEFAULT 1,
                max_retries INTEGER NOT NULL DEFAULT 0,
                retry_delay_seconds INTEGER NOT NULL DEFAULT 60,
                prevent_overlap BOOLEAN NOT NULL DEFAULT 1,
                timeout_seconds INTEGER,
                notify_channel_ids TEXT DEFAULT '[]',
                last_run_at TIMESTAMP,
                next_run_at TIMESTAMP,
                last_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE SET NULL
            )
        """)

        # Create job_executions table for execution history and log capture
        await db.execute("""
            CREATE TABLE IF NOT EXISTS job_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'running',
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                duration_seconds REAL,
                retry_attempt INTEGER NOT NULL DEFAULT 0,
                triggered_by TEXT NOT NULL DEFAULT 'scheduler',
                FOREIGN KEY (job_id) REFERENCES schedule_jobs(id) ON DELETE CASCADE
            )
        """)

        # Create notification_channels table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL,
                config TEXT NOT NULL DEFAULT '{}',
                enabled BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create incidents table for grouped failure alerts
        await db.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                severity TEXT NOT NULL DEFAULT 'warning',
                description TEXT,
                acknowledged_at TIMESTAMP,
                acknowledged_by TEXT,
                resolved_at TIMESTAMP,
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

        # Migrations run before the index block: an index over a column that a
        # migration adds cannot be created while that column is still missing.
        await _run_migrations(db)

        # Create indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_name ON scripts(name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_extension ON scripts(extension)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_language ON scripts(language)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_hash ON scripts(hash)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_mtime ON scripts(mtime)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_root ON scripts(root_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_missing ON scripts(missing_flag)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_scripts_path ON scripts(path)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_script_tags_script ON script_tags(script_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_script_tags_tag ON script_tags(tag_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_script_notes_script ON script_notes(script_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_change_log_script ON change_log(script_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_change_log_time ON change_log(event_time)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_monitor_pings_monitor ON monitor_pings(monitor_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_job_executions_job ON job_executions(job_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_job_executions_started ON job_executions(started_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_job_executions_status ON job_executions(status)")
        # Overlap prevention was a check-then-act race: two concurrent triggers
        # could both see no running execution and both insert one. A partial
        # unique index makes the database refuse the second insert.
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_executions_single_running "
            "ON job_executions(job_id) WHERE status = 'running'"
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_schedule_jobs_next_run ON schedule_jobs(next_run_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_incidents_source ON incidents(source_type, source_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_attachments_script ON attachments(script_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_attachments_note ON attachments(note_id)")

        await db.commit()
