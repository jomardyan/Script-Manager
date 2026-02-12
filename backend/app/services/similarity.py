"""
Similarity Detection service
Uses difflib for fuzzy matching to find similar scripts
"""
import difflib
from typing import List, Dict, Tuple
import aiosqlite


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio between two texts
    Returns a value between 0 and 1 (1 = identical)
    """
    matcher = difflib.SequenceMatcher(None, text1, text2)
    return matcher.ratio()


def normalize_content(content: str) -> str:
    """
    Normalize content for similarity comparison
    - Remove comments
    - Normalize whitespace
    - Convert to lowercase
    """
    lines = content.split('\n')
    normalized_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip empty lines and common comment patterns
        if not line or line.startswith('#') or line.startswith('//') or line.startswith('/*'):
            continue
        normalized_lines.append(line.lower())
    
    return '\n'.join(normalized_lines)


async def find_similar_scripts(
    db: aiosqlite.Connection,
    script_id: int,
    threshold: float = 0.7,
    limit: int = 10
) -> List[Dict]:
    """
    Find scripts similar to the given script
    
    Args:
        db: Database connection
        script_id: ID of the script to compare against
        threshold: Similarity threshold (0.0 to 1.0)
        limit: Maximum number of similar scripts to return
    
    Returns:
        List of similar scripts with similarity scores
    """
    # Get the target script's content
    async with db.execute(
        "SELECT path, name, language, size FROM scripts WHERE id = ?",
        (script_id,)
    ) as cursor:
        target = await cursor.fetchone()
        if not target:
            return []
        
        target_path, target_name, target_language, target_size = target
    
    # Read target file content
    try:
        with open(target_path, 'r', encoding='utf-8', errors='ignore') as f:
            target_content = f.read()
    except Exception:
        return []
    
    # Normalize target content
    normalized_target = normalize_content(target_content)
    
    # Find candidate scripts (same language, similar size)
    size_min = int(target_size * 0.5) if target_size else 0
    size_max = int(target_size * 2) if target_size else 999999999
    
    query = """
        SELECT id, path, name, size, hash
        FROM scripts
        WHERE id != ?
        AND missing_flag = 0
        AND language = ?
        AND size BETWEEN ? AND ?
        ORDER BY ABS(size - ?) 
        LIMIT 50
    """
    
    async with db.execute(
        query,
        (script_id, target_language, size_min, size_max, target_size)
    ) as cursor:
        candidates = await cursor.fetchall()
    
    similar_scripts = []
    
    for candidate in candidates:
        candidate_id, candidate_path, candidate_name, candidate_size, candidate_hash = candidate
        
        # Skip exact duplicates (same hash)
        if candidate_hash and candidate_hash == target.get('hash'):
            continue
        
        # Read candidate content
        try:
            with open(candidate_path, 'r', encoding='utf-8', errors='ignore') as f:
                candidate_content = f.read()
        except Exception:
            continue
        
        # Normalize candidate content
        normalized_candidate = normalize_content(candidate_content)
        
        # Calculate similarity
        similarity = calculate_similarity(normalized_target, normalized_candidate)
        
        if similarity >= threshold:
            similar_scripts.append({
                'id': candidate_id,
                'path': candidate_path,
                'name': candidate_name,
                'size': candidate_size,
                'similarity_score': round(similarity, 4),
                'similarity_percent': round(similarity * 100, 2)
            })
    
    # Sort by similarity (highest first) and limit results
    similar_scripts.sort(key=lambda x: x['similarity_score'], reverse=True)
    return similar_scripts[:limit]


async def find_all_similar_groups(
    db: aiosqlite.Connection,
    threshold: float = 0.8,
    min_group_size: int = 2
) -> List[Dict]:
    """
    Find all groups of similar scripts
    
    Args:
        db: Database connection
        threshold: Similarity threshold (0.0 to 1.0)
        min_group_size: Minimum number of scripts in a group
    
    Returns:
        List of similarity groups
    """
    # Get all scripts grouped by language
    async with db.execute(
        """
        SELECT language, COUNT(*) as count
        FROM scripts
        WHERE missing_flag = 0 AND language IS NOT NULL
        GROUP BY language
        HAVING count >= ?
        """,
        (min_group_size,)
    ) as cursor:
        languages = await cursor.fetchall()
    
    all_groups = []
    processed_scripts = set()
    
    for language_row in languages:
        language = language_row[0]
        
        # Get all scripts for this language
        async with db.execute(
            """
            SELECT id, path, name, size, hash
            FROM scripts
            WHERE language = ? AND missing_flag = 0
            ORDER BY size
            """,
            (language,)
        ) as cursor:
            scripts = await cursor.fetchall()
        
        # Compare scripts within same language
        for i, script1 in enumerate(scripts):
            script1_id = script1[0]
            
            if script1_id in processed_scripts:
                continue
            
            similar_group = [script1_id]
            
            # Find similar scripts
            similar = await find_similar_scripts(db, script1_id, threshold, limit=20)
            
            for sim in similar:
                sim_id = sim['id']
                if sim_id not in processed_scripts:
                    similar_group.append(sim_id)
                    processed_scripts.add(sim_id)
            
            if len(similar_group) >= min_group_size:
                # Get details for all scripts in group
                placeholders = ','.join('?' * len(similar_group))
                async with db.execute(
                    f"""
                    SELECT id, name, path, size
                    FROM scripts
                    WHERE id IN ({placeholders})
                    """,
                    similar_group
                ) as cursor:
                    group_scripts = await cursor.fetchall()
                
                all_groups.append({
                    'language': language,
                    'script_count': len(similar_group),
                    'scripts': [
                        {
                            'id': s[0],
                            'name': s[1],
                            'path': s[2],
                            'size': s[3]
                        }
                        for s in group_scripts
                    ]
                })
                
                processed_scripts.add(script1_id)
    
    return all_groups


async def get_similarity_matrix(
    db: aiosqlite.Connection,
    script_ids: List[int]
) -> Dict:
    """
    Generate a similarity matrix for a set of scripts
    
    Args:
        db: Database connection
        script_ids: List of script IDs to compare
    
    Returns:
        Similarity matrix and script details
    """
    if len(script_ids) < 2:
        return {'error': 'Need at least 2 scripts for comparison'}
    
    # Get script details
    placeholders = ','.join('?' * len(script_ids))
    async with db.execute(
        f"SELECT id, name, path FROM scripts WHERE id IN ({placeholders})",
        script_ids
    ) as cursor:
        scripts = await cursor.fetchall()
    
    script_dict = {s[0]: {'id': s[0], 'name': s[1], 'path': s[2]} for s in scripts}
    
    # Read all file contents
    contents = {}
    for script_id, script_info in script_dict.items():
        try:
            with open(script_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                contents[script_id] = normalize_content(content)
        except Exception:
            contents[script_id] = ""
    
    # Calculate similarity matrix
    matrix = []
    for id1 in script_ids:
        row = []
        for id2 in script_ids:
            if id1 == id2:
                score = 1.0
            else:
                score = calculate_similarity(contents[id1], contents[id2])
            row.append(round(score, 4))
        matrix.append(row)
    
    return {
        'script_ids': script_ids,
        'scripts': [script_dict[sid] for sid in script_ids],
        'similarity_matrix': matrix
    }
