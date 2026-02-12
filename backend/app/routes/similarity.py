"""
Similarity Detection API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
import aiosqlite

from app.db.database import get_db
from app.services.similarity import find_similar_scripts, find_all_similar_groups, get_similarity_matrix

router = APIRouter()


@router.get("/{script_id}")
async def get_similar_scripts(
    script_id: int,
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Similarity threshold (0.0 to 1.0)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Find scripts similar to the given script
    
    - **script_id**: ID of the script to find similar scripts for
    - **threshold**: Similarity threshold (0.0 = no similarity, 1.0 = identical)
    - **limit**: Maximum number of similar scripts to return
    """
    # Check if script exists
    async with db.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")
    
    try:
        similar = await find_similar_scripts(db, script_id, threshold, limit)
        return {
            'script_id': script_id,
            'threshold': threshold,
            'similar_count': len(similar),
            'similar_scripts': similar
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Similarity detection failed: {str(e)}")


@router.get("/groups/all")
async def get_similarity_groups(
    threshold: float = Query(0.8, ge=0.0, le=1.0, description="Similarity threshold"),
    min_group_size: int = Query(2, ge=2, le=10, description="Minimum scripts per group"),
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Find all groups of similar scripts across the entire repository
    
    This can be slow for large repositories as it compares many scripts.
    Consider using a higher threshold (e.g., 0.85) to reduce comparisons.
    
    - **threshold**: Similarity threshold for grouping
    - **min_group_size**: Minimum number of scripts required to form a group
    """
    try:
        groups = await find_all_similar_groups(db, threshold, min_group_size)
        return {
            'threshold': threshold,
            'min_group_size': min_group_size,
            'group_count': len(groups),
            'groups': groups
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Group detection failed: {str(e)}")


@router.post("/matrix")
async def similarity_matrix(
    script_ids: List[int],
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Generate a similarity matrix for a specific set of scripts
    
    Compares all provided scripts against each other and returns
    a matrix of similarity scores.
    
    - **script_ids**: List of script IDs to compare (2-20 scripts recommended)
    """
    if len(script_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 scripts for comparison")
    
    if len(script_ids) > 50:
        raise HTTPException(status_code=400, detail="Too many scripts (max 50)")
    
    try:
        matrix = await get_similarity_matrix(db, script_ids)
        return matrix
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matrix generation failed: {str(e)}")


@router.get("/compare/{script_id1}/{script_id2}")
async def compare_two_scripts(
    script_id1: int,
    script_id2: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Compare two specific scripts and get their similarity score
    
    - **script_id1**: First script ID
    - **script_id2**: Second script ID
    """
    # Verify both scripts exist
    async with db.execute(
        "SELECT id, name, path FROM scripts WHERE id IN (?, ?)",
        (script_id1, script_id2)
    ) as cursor:
        scripts = await cursor.fetchall()
        if len(scripts) != 2:
            raise HTTPException(status_code=404, detail="One or both scripts not found")
    
    try:
        matrix = await get_similarity_matrix(db, [script_id1, script_id2])
        
        # Extract the similarity score
        similarity_score = matrix['similarity_matrix'][0][1]
        
        return {
            'script1': matrix['scripts'][0],
            'script2': matrix['scripts'][1],
            'similarity_score': similarity_score,
            'similarity_percent': round(similarity_score * 100, 2),
            'similarity_level': (
                'identical' if similarity_score >= 0.95 else
                'very_high' if similarity_score >= 0.85 else
                'high' if similarity_score >= 0.70 else
                'moderate' if similarity_score >= 0.50 else
                'low'
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")
