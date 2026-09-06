"""
Full-Text Search (FTS5) service
"""
from typing import Dict

import aiosqlite

from app.db.sql import TAGS_SUBQUERY, split_tags


async def index_script_content(db: aiosqlite.Connection, script_id: int, name: str, path: str, content: str = "", notes: str = ""):
    """Index a script's content in the FTS table"""
    # Delete existing entry if any
    await db.execute("DELETE FROM scripts_fts WHERE script_id = ?", (script_id,))
    
    # Insert new entry
    await db.execute(
        """
        INSERT INTO scripts_fts (script_id, name, path, content, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (script_id, name, path, content, notes)
    )
    await db.commit()


async def update_script_notes_fts(db: aiosqlite.Connection, script_id: int):
    """Update FTS entry with latest notes for a script"""
    # Get script info
    async with db.execute(
        "SELECT name, path FROM scripts WHERE id = ?",
        (script_id,)
    ) as cursor:
        script_row = await cursor.fetchone()
        if not script_row:
            return
        name, path = script_row
    
    # Get notes
    async with db.execute(
        "SELECT GROUP_CONCAT(content, ' ') FROM script_notes WHERE script_id = ?",
        (script_id,)
    ) as cursor:
        notes_row = await cursor.fetchone()
        notes = notes_row[0] if notes_row and notes_row[0] else ""
    
    # Get existing content from FTS
    async with db.execute(
        "SELECT content FROM scripts_fts WHERE script_id = ?",
        (script_id,)
    ) as cursor:
        fts_row = await cursor.fetchone()
        content = fts_row[0] if fts_row else ""
    
    # Update FTS
    await db.execute("DELETE FROM scripts_fts WHERE script_id = ?", (script_id,))
    await db.execute(
        "INSERT INTO scripts_fts (script_id, name, path, content, notes) VALUES (?, ?, ?, ?, ?)",
        (script_id, name, path, content, notes)
    )
    await db.commit()


def build_match_expression(query: str, search_content: bool, search_notes: bool) -> str:
    """
    Turn user input into a safe FTS5 MATCH expression.

    The query is quoted as a phrase so FTS5 operators the user typed (AND, OR,
    NEAR, ``*``, ``:``, unbalanced quotes) are matched literally instead of
    raising a syntax error or changing the meaning of the search.

    The column filter is what makes ``search_content`` and ``search_notes``
    actually do something: previously both flags were computed and then
    ignored, so every search matched content and notes regardless.
    """
    columns = ["name", "path"]
    if search_content:
        columns.append("content")
    if search_notes:
        columns.append("notes")

    escaped = (query or "").replace('"', '""').strip()
    if not escaped:
        raise ValueError("Search query cannot be empty")

    phrase = f'"{escaped}"'
    # {col1 col2} : <phrase> restricts the match to those columns.
    return "{" + " ".join(columns) + "} : " + phrase


async def search_fts(
    db: aiosqlite.Connection,
    query: str,
    search_content: bool = True,
    search_notes: bool = True,
    page: int = 1,
    page_size: int = 50
) -> Dict:
    """
    Perform full-text search across scripts.
    Returns paginated results with match ranks.
    """
    fts_query = build_match_expression(query, search_content, search_notes)

    count_query = """
        SELECT COUNT(DISTINCT fts.script_id)
        FROM scripts_fts fts
        JOIN scripts s ON fts.script_id = s.id
        WHERE scripts_fts MATCH ? AND s.missing_flag = 0
    """
    async with db.execute(count_query, (fts_query,)) as cursor:
        total = (await cursor.fetchone())[0]

    offset = (page - 1) * page_size
    search_query = f"""
        SELECT
            fts.script_id,
            s.name,
            s.path,
            s.extension,
            s.language,
            s.size,
            s.mtime,
            st.status,
            {TAGS_SUBQUERY} AS tags,
            rank
        FROM scripts_fts fts
        JOIN scripts s ON fts.script_id = s.id
        LEFT JOIN script_status st ON s.id = st.script_id
        WHERE scripts_fts MATCH ? AND s.missing_flag = 0
        GROUP BY fts.script_id
        ORDER BY rank
        LIMIT ? OFFSET ?
    """

    async with db.execute(search_query, (fts_query, page_size, offset)) as cursor:
        rows = await cursor.fetchall()
        items = []
        for row in rows:
            items.append({
                'id': row[0],
                'name': row[1],
                'path': row[2],
                'extension': row[3],
                'language': row[4],
                'size': row[5],
                'mtime': row[6],
                'status': row[7],
                'tags': split_tags(row[8]),
                'rank': row[9],
            })

    total_pages = (total + page_size - 1) // page_size

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages
    }


async def remove_from_index(db: aiosqlite.Connection, script_id: int):
    """Drop a script from the FTS index (used when it is deleted or goes missing)."""
    await db.execute("DELETE FROM scripts_fts WHERE script_id = ?", (script_id,))


async def rebuild_fts_index(db: aiosqlite.Connection, root_id: int = None):
    """Rebuild the FTS index for all scripts or a specific root"""
    # Clear FTS table
    if root_id:
        # Delete entries for specific root
        await db.execute("""
            DELETE FROM scripts_fts 
            WHERE script_id IN (SELECT id FROM scripts WHERE root_id = ?)
        """, (root_id,))
    else:
        # Clear all
        await db.execute("DELETE FROM scripts_fts")
    
    # Get scripts to index
    if root_id:
        query = "SELECT id, name, path FROM scripts WHERE root_id = ? AND missing_flag = 0"
        params = (root_id,)
    else:
        query = "SELECT id, name, path FROM scripts WHERE missing_flag = 0"
        params = ()
    
    async with db.execute(query, params) as cursor:
        scripts = await cursor.fetchall()
    
    indexed_count = 0
    for script in scripts:
        script_id, name, path = script
        
        # Get notes
        async with db.execute(
            "SELECT GROUP_CONCAT(content, ' ') FROM script_notes WHERE script_id = ?",
            (script_id,)
        ) as cursor:
            notes_row = await cursor.fetchone()
            notes = notes_row[0] if notes_row and notes_row[0] else ""
        
        # Read content if file exists (only for indexed roots)
        content = ""
        try:
            # Check if content indexing is enabled for this root
            async with db.execute(
                """
                SELECT fr.enable_content_indexing 
                FROM folder_roots fr 
                JOIN scripts s ON fr.id = s.root_id 
                WHERE s.id = ?
                """,
                (script_id,)
            ) as cursor:
                root_row = await cursor.fetchone()
                if root_row and root_row[0]:
                    # Read file content
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(100000)  # Limit to first 100KB
        except Exception:
            # Intentionally ignore any errors while reading file content;
            # the script will still be indexed using metadata and notes only.
            pass
        
        # Index in FTS
        await db.execute(
            "INSERT INTO scripts_fts (script_id, name, path, content, notes) VALUES (?, ?, ?, ?, ?)",
            (script_id, name, path, content, notes)
        )
        indexed_count += 1
    
    await db.commit()
    return indexed_count
