"""
Script Manager Backend Application
Main entry point for the FastAPI application
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
from app.routes import folder_roots, scripts, tags, notes, search, folders, saved_searches, fts, watch, similarity, attachments

app = FastAPI(
    title="Script Manager API",
    description="API for managing script file collections",
    version="1.0.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
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

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_db()

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
