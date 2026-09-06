"""
Script Manager Backend Application
Main entry point for the FastAPI application
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.db import database as db_module
from app.db.database import init_db
from app.routes import (
    attachments, auth, folder_roots, folders, fts, monitors, notes,
    notifications, saved_searches, schedules, scripts, search, setup,
    similarity, tags, watch,
)
from app.services.scheduler import SchedulerHandle, scheduler_enabled
from app.utils.logging_config import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)

scheduler_handle = SchedulerHandle()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS is only meaningful over TLS, and sending it over plain HTTP can
        # lock users out of a local http:// deployment for a year.
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("Starting Script Manager API...")
    await init_db()

    from app.services.auth import init_default_admin, init_default_roles, sync_role_permissions

    async with db_module.connection() as db:
        await init_default_roles(db)
        await sync_role_permissions(db)

        # Repair databases written by releases that ran without foreign keys
        # enabled, which left children behind after a parent was deleted.
        removed = await db_module.cleanup_orphans(db)
        if removed:
            logger.warning("Removed orphaned rows left by earlier deletes: %s", removed)

        # Only create the fallback admin account for existing installations
        # that already completed setup before the wizard was introduced.
        # Fresh installs must go through the wizard to create their admin account.
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'setup_completed'"
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0] == "true":
            await init_default_admin(db)

    if scheduler_enabled():
        scheduler_handle.start(db_module.DB_PATH)
    else:
        logger.info("Background scheduler disabled (ENABLE_SCHEDULER=false)")

    logger.info("Script Manager API started successfully")
    yield

    logger.info("Shutting down Script Manager API...")
    await scheduler_handle.stop()

    # Release filesystem watchers so the process can exit cleanly.
    try:
        from app.services.watch import get_watch_manager

        await get_watch_manager(db_module.DB_PATH).stop_all()
    except Exception as exc:  # noqa: BLE001 - shutdown must not raise
        logger.warning("Could not stop watch manager cleanly: %s", exc)


# Get allowed origins from environment variable
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app = FastAPI(
    title="Script Manager API",
    description="API for managing script file collections",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend.
# Credentials cannot be combined with a wildcard origin, and doing so would let
# any site read authenticated responses, so "*" downgrades to credential-less.
allow_credentials = "*" not in ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Script content and long result pages compress very well.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(setup.router, prefix="/api/setup", tags=["Setup Wizard"])
app.include_router(folder_roots.router, prefix="/api/folder-roots", tags=["Folder Roots"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["Scripts"])
app.include_router(tags.router, prefix="/api/tags", tags=["Tags"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(folders.router, prefix="/api/folders", tags=["Folders"])
app.include_router(saved_searches.router, prefix="/api/saved-searches", tags=["Saved Searches"])
app.include_router(fts.router, prefix="/api/fts", tags=["Full-Text Search"])
app.include_router(watch.router, prefix="/api/watch", tags=["Watch Mode"])
app.include_router(similarity.router, prefix="/api/similarity", tags=["Similarity Detection"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["Attachments"])
app.include_router(monitors.router, prefix="/api/monitors", tags=["Monitors"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["Schedules"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Script Manager API",
        "version": app.version,
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint used by Docker and load balancers."""
    healthy = True
    detail = "ok"
    try:
        async with db_module.connection() as db:
            await db.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - the point is to report, not raise
        healthy = False
        detail = f"database unavailable: {exc}"

    return {
        "status": "healthy" if healthy else "degraded",
        "database": detail,
        "scheduler": "running" if scheduler_enabled() else "disabled",
        "version": app.version,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").strip().lower() in ("1", "true", "yes", "on")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
