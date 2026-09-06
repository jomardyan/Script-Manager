"""
Script scanning and indexing service
"""
import asyncio
import hashlib
import fnmatch
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Language detection based on extensions
EXTENSION_LANGUAGE_MAP = {
    '.py': 'Python',
    '.ps1': 'PowerShell',
    '.psm1': 'PowerShell',
    '.sh': 'Bash',
    '.bat': 'Batch',
    '.cmd': 'Batch',
    '.sql': 'SQL',
    '.js': 'JavaScript',
    '.ts': 'TypeScript',
    '.yml': 'YAML',
    '.yaml': 'YAML',
    '.json': 'JSON',
    '.tf': 'Terraform',
    '.rb': 'Ruby',
    '.pl': 'Perl',
    '.php': 'PHP',
    '.go': 'Go',
    '.rs': 'Rust',
    '.java': 'Java',
    '.cs': 'C#',
    '.cpp': 'C++',
    '.c': 'C',
    '.r': 'R'
}

def get_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of file content"""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return ""

def get_line_count(file_path: str) -> int:
    """Count lines in a text file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def detect_language(file_path: str) -> Optional[str]:
    """Detect script language based on extension"""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext)

def is_script_file(file_path: str) -> bool:
    """Check if file is a recognized script type"""
    ext = Path(file_path).suffix.lower()
    return ext in EXTENSION_LANGUAGE_MAP

def match_patterns(path: str, patterns: Optional[str]) -> bool:
    """Check if path matches any of the glob patterns"""
    if not patterns:
        return True
    
    pattern_list = [p.strip() for p in patterns.split(',') if p.strip()]
    path_str = str(path)
    
    for pattern in pattern_list:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(Path(path_str).name, pattern):
            return True
    return False

def _scan_directory_sync(
    root_path: str,
    recursive: bool = True,
    include_patterns: Optional[str] = None,
    exclude_patterns: Optional[str] = None,
    follow_symlinks: bool = False,
    max_file_size: int = 10485760,
) -> Tuple[List[Dict], List[str]]:
    """Blocking directory walk. Returns (script metadata, folder paths)."""
    scripts: List[Dict] = []
    folders: List[str] = []
    root_path_obj = Path(root_path)

    if not root_path_obj.exists():
        raise ValueError(f"Path does not exist: {root_path}")

    if not root_path_obj.is_dir():
        raise ValueError(f"Path is not a directory: {root_path}")

    # Following symlinks can otherwise walk a cycle forever; track real paths.
    visited: Set[str] = set()

    def scan_path(path: Path):
        try:
            real = os.path.realpath(path)
            if real in visited:
                return
            visited.add(real)

            for item in sorted(path.iterdir(), key=lambda p: p.name):
                # Skip if exclude pattern matches
                if exclude_patterns and match_patterns(str(item), exclude_patterns):
                    continue

                # Handle symlinks
                if item.is_symlink() and not follow_symlinks:
                    continue

                # Recursively scan directories
                if item.is_dir():
                    folders.append(str(item.absolute()))
                    if recursive:
                        scan_path(item)
                    continue

                # Process files
                if item.is_file():
                    if not is_script_file(str(item)):
                        continue

                    if include_patterns and not match_patterns(str(item), include_patterns):
                        continue

                    try:
                        stat = item.stat()
                    except OSError:
                        continue

                    # Hashing and line counting read the whole file, so the
                    # size limit has to be checked before either runs.
                    if stat.st_size > max_file_size:
                        continue

                    try:
                        scripts.append({
                            'path': str(item.absolute()),
                            'name': item.name,
                            'extension': item.suffix.lower(),
                            'language': detect_language(str(item)),
                            'size': stat.st_size,
                            'mtime': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                            'hash': get_file_hash(str(item)),
                            'line_count': get_line_count(str(item)),
                        })
                    except OSError as exc:
                        logger.warning("Error processing file %s: %s", item, exc)
                        continue
        except PermissionError:
            logger.warning("Permission denied while scanning %s", path)
        except OSError as exc:
            logger.warning("Error scanning %s: %s", path, exc)

    scan_path(root_path_obj)
    return scripts, folders


async def scan_directory(
    root_path: str,
    recursive: bool = True,
    include_patterns: Optional[str] = None,
    exclude_patterns: Optional[str] = None,
    follow_symlinks: bool = False,
    max_file_size: int = 10485760,
) -> List[Dict]:
    """
    Scan a directory for script files.

    The walk is blocking (stat, hashing, line counts), so it runs in a worker
    thread; running it inline would freeze the whole API for the duration of
    a large scan.
    """
    scripts, _folders = await asyncio.to_thread(
        _scan_directory_sync, root_path, recursive, include_patterns,
        exclude_patterns, follow_symlinks, max_file_size,
    )
    return scripts


async def scan_directory_detailed(
    root_path: str,
    recursive: bool = True,
    include_patterns: Optional[str] = None,
    exclude_patterns: Optional[str] = None,
    follow_symlinks: bool = False,
    max_file_size: int = 10485760,
) -> Tuple[List[Dict], List[str]]:
    """Like scan_directory but also returns the folders encountered."""
    return await asyncio.to_thread(
        _scan_directory_sync, root_path, recursive, include_patterns,
        exclude_patterns, follow_symlinks, max_file_size,
    )


async def get_duplicate_scripts(db) -> List[Dict]:
    """Find scripts with duplicate content hashes"""
    query = """
        SELECT hash, COUNT(*) as count, GROUP_CONCAT(path, '|') as paths
        FROM scripts
        WHERE hash IS NOT NULL AND hash != '' AND missing_flag = 0
        GROUP BY hash
        HAVING count > 1
        ORDER BY count DESC
    """
    
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()
        duplicates = []
        for row in rows:
            duplicates.append({
                'hash': row[0],
                'count': row[1],
                'paths': row[2].split('|') if row[2] else []
            })
        return duplicates
