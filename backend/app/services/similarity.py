"""
Similarity Detection service
Uses difflib for fuzzy matching to find similar scripts
"""
import asyncio
import difflib
import logging
import os
from typing import Dict, List, Optional, Set

import aiosqlite

logger = logging.getLogger(__name__)

# Files larger than this are skipped: SequenceMatcher is quadratic in the
# input length, so comparing megabyte files stalls the worker thread.
MAX_COMPARE_BYTES = 1024 * 1024

# Upper bound on how many scripts a single repository-wide sweep will compare.
# The comparison is inherently O(n^2), so an unbounded sweep over a large
# collection never returns.
MAX_GROUP_SCAN_SCRIPTS = 400


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio between two texts.
    Returns a value between 0 and 1 (1 = identical).

    ``autojunk`` must stay off: difflib's heuristic treats any character
    appearing in more than 1% of a sequence longer than 200 items as junk,
    which for source code means spaces, newlines and common letters. With it
    enabled, files over roughly 2 KB score near zero no matter how alike they
    are, so every similarity result was meaningless for real scripts.
    """
    matcher = difflib.SequenceMatcher(None, text1, text2, autojunk=False)
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


def _read_normalized(path: str) -> Optional[str]:
    """Read and normalize a file, or None when it is unreadable or too large."""
    try:
        if os.path.getsize(path) > MAX_COMPARE_BYTES:
            return None
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            return normalize_content(fh.read())
    except OSError:
        return None


async def _load_normalized(paths: Dict[int, str]) -> Dict[int, str]:
    """
    Read and normalize several files off the event loop.

    Reading is blocking and the callers compare every pair, so loading each
    file once here replaces the previous behaviour of re-reading a file from
    disk for every comparison it took part in.
    """
    def _load_all() -> Dict[int, str]:
        loaded = {}
        for script_id, path in paths.items():
            content = _read_normalized(path)
            if content is not None:
                loaded[script_id] = content
        return loaded

    return await asyncio.to_thread(_load_all)


async def _score_pairs(pairs, contents) -> List[float]:
    """Score a list of (id1, id2) pairs off the event loop."""
    def _run() -> List[float]:
        return [
            calculate_similarity(contents.get(a, ""), contents.get(b, ""))
            for a, b in pairs
        ]

    return await asyncio.to_thread(_run)


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
    async with db.execute(
        "SELECT path, name, language, size, hash FROM scripts WHERE id = ?",
        (script_id,)
    ) as cursor:
        target = await cursor.fetchone()
        if not target:
            return []
        target_path, _target_name, target_language, target_size, target_hash = target

    normalized_target = await asyncio.to_thread(_read_normalized, target_path)
    if normalized_target is None:
        return []

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

    # Skip exact duplicates (same hash) - those belong in the duplicates view.
    candidates = [
        c for c in candidates
        if not (c[4] and target_hash and c[4] == target_hash)
    ]
    if not candidates:
        return []

    contents = await _load_normalized({c[0]: c[1] for c in candidates})
    pairs = [(script_id, c[0]) for c in candidates if c[0] in contents]
    contents[script_id] = normalized_target
    scores = await _score_pairs(pairs, contents)

    similar_scripts = []
    by_id = {c[0]: c for c in candidates}
    for (_target, candidate_id), similarity in zip(pairs, scores):
        if similarity < threshold:
            continue
        candidate = by_id[candidate_id]
        similar_scripts.append({
            'id': candidate[0],
            'path': candidate[1],
            'name': candidate[2],
            'size': candidate[3],
            'similarity_score': round(similarity, 4),
            'similarity_percent': round(similarity * 100, 2)
        })

    similar_scripts.sort(key=lambda x: x['similarity_score'], reverse=True)
    return similar_scripts[:limit]


async def find_all_similar_groups(
    db: aiosqlite.Connection,
    threshold: float = 0.8,
    min_group_size: int = 2,
    max_scripts: int = MAX_GROUP_SCAN_SCRIPTS,
) -> Dict:
    """
    Find groups of similar scripts across the collection.

    Each language is handled separately, every file is read once, and the
    number of scripts considered is capped: the comparison is quadratic, so an
    unbounded sweep over a large collection would never finish.

    Returns a dict with the groups plus how much of the collection was covered,
    so the caller can tell the user when results were truncated.
    """
    async with db.execute(
        """
        SELECT language, COUNT(*) as count
        FROM scripts
        WHERE missing_flag = 0 AND language IS NOT NULL
        GROUP BY language
        HAVING count >= ?
        ORDER BY count DESC
        """,
        (min_group_size,)
    ) as cursor:
        languages = await cursor.fetchall()

    all_groups: List[Dict] = []
    considered = 0
    truncated = False

    for language_row in languages:
        if considered >= max_scripts:
            truncated = True
            break

        language = language_row[0]
        remaining = max_scripts - considered

        async with db.execute(
            """
            SELECT id, path, name, size
            FROM scripts
            WHERE language = ? AND missing_flag = 0
            ORDER BY size
            LIMIT ?
            """,
            (language, remaining)
        ) as cursor:
            scripts = await cursor.fetchall()

        if (language_row[1] or 0) > len(scripts):
            truncated = True
        if len(scripts) < min_group_size:
            continue

        considered += len(scripts)
        details = {s[0]: {'id': s[0], 'name': s[2], 'path': s[1], 'size': s[3]} for s in scripts}
        contents = await _load_normalized({s[0]: s[1] for s in scripts})

        ids = [s[0] for s in scripts if s[0] in contents]
        # Upper triangle only: similarity is symmetric, so comparing both
        # directions doubled the work for no extra information.
        pairs = [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]
        scores = await _score_pairs(pairs, contents)

        # Union-find over the pairs above the threshold groups transitively
        # similar scripts together.
        parent = {sid: sid for sid in ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for (a, b), score in zip(pairs, scores):
            if score >= threshold:
                union(a, b)

        clusters: Dict[int, Set[int]] = {}
        for sid in ids:
            clusters.setdefault(find(sid), set()).add(sid)

        for members in clusters.values():
            if len(members) < min_group_size:
                continue
            all_groups.append({
                'language': language,
                'script_count': len(members),
                'scripts': [details[m] for m in sorted(members)],
            })

    all_groups.sort(key=lambda g: g['script_count'], reverse=True)
    return {
        'groups': all_groups,
        'scripts_compared': considered,
        'truncated': truncated,
        'max_scripts': max_scripts,
    }


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

    Raises:
        ValueError: when fewer than two scripts are given or an id is unknown.
    """
    # De-duplicate while preserving the caller's order.
    ordered_ids: List[int] = []
    for sid in script_ids:
        if sid not in ordered_ids:
            ordered_ids.append(sid)

    if len(ordered_ids) < 2:
        raise ValueError("Need at least 2 distinct scripts for comparison")

    placeholders = ','.join('?' * len(ordered_ids))
    async with db.execute(
        f"SELECT id, name, path FROM scripts WHERE id IN ({placeholders})",
        ordered_ids
    ) as cursor:
        scripts = await cursor.fetchall()

    script_dict = {s[0]: {'id': s[0], 'name': s[1], 'path': s[2]} for s in scripts}

    # Previously a missing id produced a KeyError and a 500; name it instead.
    missing = [sid for sid in ordered_ids if sid not in script_dict]
    if missing:
        raise ValueError(
            f"Unknown script id(s): {', '.join(str(m) for m in missing)}"
        )

    contents = await _load_normalized({sid: script_dict[sid]['path'] for sid in ordered_ids})

    pairs = [
        (ordered_ids[i], ordered_ids[j])
        for i in range(len(ordered_ids))
        for j in range(i + 1, len(ordered_ids))
    ]
    scores = await _score_pairs(pairs, contents)
    lookup = {pair: round(score, 4) for pair, score in zip(pairs, scores)}

    matrix = []
    for id1 in ordered_ids:
        row = []
        for id2 in ordered_ids:
            if id1 == id2:
                row.append(1.0)
            else:
                key = (id1, id2) if (id1, id2) in lookup else (id2, id1)
                row.append(lookup.get(key, 0.0))
        matrix.append(row)

    return {
        'script_ids': ordered_ids,
        'scripts': [script_dict[sid] for sid in ordered_ids],
        'similarity_matrix': matrix,
        'unreadable_script_ids': [sid for sid in ordered_ids if sid not in contents],
    }
