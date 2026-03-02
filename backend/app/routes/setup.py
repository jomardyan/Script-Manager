"""
Setup Wizard API endpoints for first-time installation
"""
import json
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

import aiosqlite

from app.db.database import get_db

router = APIRouter()


class DatabaseConfig(BaseModel):
    type: str  # "sqlite", "mysql", "postgresql"
    sqlite_path: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class AdminConfig(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None


class SetupCompleteRequest(BaseModel):
    mode: str  # "demo", "production", "development"
    database: DatabaseConfig
    admin: Optional[AdminConfig] = None


async def _save_setting(db: aiosqlite.Connection, key: str, value: str):
    """Save or update an app setting"""
    await db.execute(
        """INSERT INTO app_settings (key, value)
           VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
               updated_at = CURRENT_TIMESTAMP""",
        (key, value),
    )


async def _seed_demo_data(db: aiosqlite.Connection):
    """Seed the database with demo/sample data"""
    demo_path = os.path.join(tempfile.gettempdir(), "script-manager-demo")
    os.makedirs(demo_path, exist_ok=True)

    # Avoid re-seeding
    async with db.execute(
        "SELECT id FROM folder_roots WHERE path = ?", (demo_path,)
    ) as cursor:
        if await cursor.fetchone():
            return

    cursor = await db.execute(
        """INSERT INTO folder_roots (path, name, recursive, enable_content_indexing)
           VALUES (?, ?, ?, ?)""",
        (demo_path, "Demo Scripts", True, True),
    )
    root_id = cursor.lastrowid

    # Sample tags
    tag_names = [
        ("automation", "scripts", "#3498db"),
        ("utility", "scripts", "#2ecc71"),
        ("backup", "scripts", "#e74c3c"),
        ("monitoring", "devops", "#9b59b6"),
        ("deployment", "devops", "#e67e22"),
    ]
    tag_ids = []
    for name, group, color in tag_names:
        try:
            cur = await db.execute(
                "INSERT INTO tags (name, group_name, color) VALUES (?, ?, ?)",
                (name, group, color),
            )
            tag_ids.append(cur.lastrowid)
        except Exception:
            pass

    # Sample scripts
    sample_scripts = [
        (
            "backup.sh",
            ".sh",
            "bash",
            1024,
            5,
            "#!/bin/bash\n# Daily backup script\necho 'Starting backup...'\n"
            "rsync -av /home/ /backup/\necho 'Backup complete!'",
        ),
        (
            "deploy.py",
            ".py",
            "python",
            2048,
            10,
            "#!/usr/bin/env python3\n# Deployment automation\nimport subprocess\n\n"
            "def deploy(env):\n    print(f'Deploying to {env}...')\n"
            "    subprocess.run(['git', 'pull'])\n\ndeploy('staging')",
        ),
        (
            "monitor.sh",
            ".sh",
            "bash",
            512,
            6,
            "#!/bin/bash\n# System monitor\necho 'CPU:'\ntop -bn1 | grep 'Cpu(s)'\n"
            "echo 'Memory:'\nfree -h",
        ),
        (
            "cleanup.py",
            ".py",
            "python",
            768,
            8,
            "#!/usr/bin/env python3\n# Remove stale log files\nimport os, time\n\n"
            "def cleanup(directory, days=30):\n    cutoff = time.time() - days * 86400\n"
            "    for f in os.listdir(directory):\n        path = os.path.join(directory, f)\n"
            "        if os.path.getmtime(path) < cutoff:\n            os.remove(path)",
        ),
        (
            "health_check.sh",
            ".sh",
            "bash",
            384,
            5,
            "#!/bin/bash\n# Health check\nif curl -sf http://localhost:8000/health; then\n"
            "    echo 'Service healthy'\nelse\n    echo 'Service down!'; exit 1\nfi",
        ),
    ]

    script_ids = []
    for name, ext, lang, size, lines, content in sample_scripts:
        script_path = os.path.join(demo_path, name)
        try:
            with open(script_path, "w") as fh:
                fh.write(content)
        except OSError:
            pass
        cur = await db.execute(
            """INSERT OR IGNORE INTO scripts
               (root_id, path, name, extension, language, size, line_count, missing_flag)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (root_id, script_path, name, ext, lang, size, lines, False),
        )
        if cur.lastrowid:
            script_ids.append(cur.lastrowid)

    # Assign tags (backup→backup, deploy→deployment+automation, monitor→monitoring,
    # cleanup→utility, health_check→monitoring)
    assignments = []
    tag_map = {t[0]: i for i, t in enumerate(tag_names)}
    script_tag_pairs = [
        (0, "backup"),
        (1, "deployment"),
        (1, "automation"),
        (2, "monitoring"),
        (3, "utility"),
        (4, "monitoring"),
    ]
    for script_idx, tag_name in script_tag_pairs:
        if script_idx < len(script_ids) and tag_name in tag_map:
            tid_idx = tag_map[tag_name]
            if tid_idx < len(tag_ids) and tag_ids[tid_idx]:
                assignments.append((script_ids[script_idx], tag_ids[tid_idx]))

    for sid, tid in assignments:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO script_tags (script_id, tag_id) VALUES (?, ?)",
                (sid, tid),
            )
        except Exception:
            pass


@router.get("/status")
async def get_setup_status(db: aiosqlite.Connection = Depends(get_db)):
    """Check whether the first-time setup has been completed."""
    try:
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'setup_completed'"
        ) as cursor:
            row = await cursor.fetchone()
    except Exception:
        return {"setup_completed": False, "mode": None}

    if row and row[0] == "true":
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'app_mode'"
        ) as cursor:
            mode_row = await cursor.fetchone()
        return {
            "setup_completed": True,
            "mode": mode_row[0] if mode_row else "production",
        }

    return {"setup_completed": False, "mode": None}


@router.post("/demo")
async def start_demo_mode(db: aiosqlite.Connection = Depends(get_db)):
    """Activate demo mode and seed sample data."""
    await _save_setting(db, "app_mode", "demo")
    await _seed_demo_data(db)
    await _save_setting(db, "setup_completed", "true")
    await db.commit()
    return {"message": "Demo mode activated", "mode": "demo"}


@router.post("/complete")
async def complete_setup(
    config: SetupCompleteRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Complete the setup wizard with the provided configuration."""
    if config.mode not in ("demo", "production", "development"):
        raise HTTPException(status_code=400, detail="Invalid mode. Choose demo, production, or development.")

    await _save_setting(db, "app_mode", config.mode)

    # Persist DB config (omit plaintext password)
    db_meta = config.database.model_dump()
    db_meta.pop("password", None)
    await _save_setting(db, "db_config", json.dumps(db_meta))
    await _save_setting(db, "db_type", config.database.type)

    if config.mode == "demo":
        await _seed_demo_data(db)
    elif config.admin:
        # Create admin account for production / development
        from app.services.auth import get_password_hash, validate_password_strength

        is_valid, error_msg = validate_password_strength(config.admin.password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        async with db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (config.admin.username, config.admin.email),
        ) as cursor:
            existing = await cursor.fetchone()

        if not existing:
            hashed = get_password_hash(config.admin.password)
            cur = await db.execute(
                """INSERT INTO users
                   (username, email, full_name, hashed_password, is_active, is_superuser)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    config.admin.username,
                    config.admin.email,
                    config.admin.full_name,
                    hashed,
                    True,
                    True,
                ),
            )
            user_id = cur.lastrowid
            # Assign admin role
            async with db.execute(
                "SELECT id FROM roles WHERE name = ?", ("admin",)
            ) as cur2:
                role_row = await cur2.fetchone()
            if role_row:
                await db.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                    (user_id, role_row[0]),
                )

    await _save_setting(db, "setup_completed", "true")
    await db.commit()
    return {
        "message": "Setup completed successfully",
        "mode": config.mode,
        "db_type": config.database.type,
    }


@router.post("/test-db")
async def test_database_connection(config: DatabaseConfig):
    """Test a database connection before committing to setup."""
    if config.type == "sqlite":
        return {"success": True, "message": "SQLite is ready — no connection test needed."}
    if config.type == "mysql":
        return await _test_mysql(config)
    if config.type == "postgresql":
        return await _test_postgresql(config)
    raise HTTPException(status_code=400, detail="Unknown database type")


async def _test_mysql(config: DatabaseConfig):
    try:
        import aiomysql  # type: ignore

        conn = await aiomysql.connect(
            host=config.host or "localhost",
            port=config.port or 3306,
            user=config.username or "",
            password=config.password or "",
            db=config.database_name or "",
        )
        conn.close()
        await conn.wait_closed()
        return {"success": True, "message": "MySQL connection successful"}
    except ImportError:
        return {
            "success": False,
            "message": "MySQL driver not installed. Run: pip install aiomysql",
        }
    except Exception as exc:
        return {"success": False, "message": f"Connection failed: {exc}"}


async def _test_postgresql(config: DatabaseConfig):
    try:
        import asyncpg  # type: ignore

        conn = await asyncpg.connect(
            host=config.host or "localhost",
            port=config.port or 5432,
            user=config.username or "",
            password=config.password or "",
            database=config.database_name or "",
        )
        await conn.close()
        return {"success": True, "message": "PostgreSQL connection successful"}
    except ImportError:
        return {
            "success": False,
            "message": "PostgreSQL driver not installed. Run: pip install asyncpg",
        }
    except Exception as exc:
        return {"success": False, "message": f"Connection failed: {exc}"}
