"""
Script Manager Backend Application
Main entry point for the FastAPI application
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.database import init_db
from app.routes import folder_roots, scripts, tags, notes, search, folders, saved_searches, fts, watch, similarity, attachments, auth, setup, monitors, schedules, notifications
from app.utils.logging_config import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Script Manager API...")
    await init_db()

    # Initialize auth system
    from app.db.database import DB_PATH
    import aiosqlite
    from app.services.auth import init_default_roles, init_default_admin

    async with aiosqlite.connect(DB_PATH) as db:
        await init_default_roles(db)

        # Only create the fallback admin/admin account for existing installations
        # that already completed setup before the wizard was introduced.
        # Fresh installs must go through the wizard to create their admin account.
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'setup_completed'"
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0] == "true":
            await init_default_admin(db)

    logger.info("Script Manager API started successfully")
    yield

    # Shutdown
    logger.info("Shutting down Script Manager API...")


# Get allowed origins from environment variable
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173"
).split(",")

app = FastAPI(
    title="Script Manager API",
    description="API for managing script file collections",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

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
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
