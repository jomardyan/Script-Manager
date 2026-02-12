"""
Full-Text Search API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

from app.db.database import get_db
from app.models.schemas import FTSSearchRequest, PaginatedResponse
from app.services.fts import search_fts, rebuild_fts_index

router = APIRouter()

@router.post("/", response_model=PaginatedResponse)
async def fts_search(
    search: FTSSearchRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Perform full-text search across script content and notes
    Requires FTS indexing to be enabled on folder roots
    """
    try:
        result = await search_fts(
            db,
            search.query,
            search.search_content,
            search.search_notes,
            search.page,
            search.page_size
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FTS search failed: {str(e)}")

@router.post("/rebuild")
async def rebuild_index(
    root_id: int = None,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Rebuild the FTS index for all scripts or a specific root
    This will read file contents and re-index everything
    """
    try:
        count = await rebuild_fts_index(db, root_id)
        return {
            "message": "FTS index rebuilt successfully",
            "indexed_count": count,
            "root_id": root_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index rebuild failed: {str(e)}")

@router.get("/status")
async def fts_status(db: aiosqlite.Connection = Depends(get_db)):
    """Get FTS index status and statistics"""
    # Count indexed scripts
    async with db.execute("SELECT COUNT(*) FROM scripts_fts") as cursor:
        indexed_count = (await cursor.fetchone())[0]
    
    # Count total scripts
    async with db.execute("SELECT COUNT(*) FROM scripts WHERE missing_flag = 0") as cursor:
        total_count = (await cursor.fetchone())[0]
    
    # Get roots with indexing enabled
    async with db.execute(
        "SELECT id, name, path FROM folder_roots WHERE enable_content_indexing = 1"
    ) as cursor:
        roots = await cursor.fetchall()
        indexed_roots = [{"id": r[0], "name": r[1], "path": r[2]} for r in roots]
    
    return {
        "indexed_scripts": indexed_count,
        "total_scripts": total_count,
        "coverage_percent": round((indexed_count / total_count * 100) if total_count > 0 else 0, 2),
        "indexed_roots": indexed_roots
    }
