"""
Authentication service
Handles JWT tokens, password hashing, and user authentication
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

# Placeholder that shipped in older .env.example files. Treating it as "unset"
# stops a well-known signing key from silently protecting a real deployment.
_INSECURE_PLACEHOLDERS = {
    "",
    "your-secret-key-change-this-in-production",
    "change-me",
    "changeme",
    "secret",
}


def _resolve_secret_key() -> str:
    """
    Resolve the JWT signing key.

    Order of preference:
      1. SECRET_KEY from the environment (the only option for multi-process
         deployments, since every worker must sign with the same key).
      2. A random key persisted next to the database, generated on first run.

    A generated key keeps single-node installs secure by default while still
    surviving restarts, which an in-memory key would not.
    """
    env_key = (os.getenv("SECRET_KEY") or "").strip()
    if env_key and env_key.lower() not in _INSECURE_PLACEHOLDERS:
        return env_key

    if env_key:
        logger.warning(
            "SECRET_KEY is set to a well-known placeholder value and is being ignored. "
            "Set a strong SECRET_KEY in the environment for production deployments."
        )

    key_path = Path(os.getenv("SECRET_KEY_FILE", "./data/.secret_key"))
    try:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            stored = key_path.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        generated = secrets.token_urlsafe(64)
        key_path.write_text(generated, encoding="utf-8")
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
        logger.warning(
            "SECRET_KEY was not provided; generated one at %s. "
            "Set SECRET_KEY explicitly if you run more than one backend process.",
            key_path,
        )
        return generated
    except OSError as exc:
        # Read-only filesystem: fall back to a process-local key. Tokens will
        # not survive a restart, which is safer than a predictable key.
        logger.error(
            "Could not persist a generated SECRET_KEY (%s); using an ephemeral key. "
            "Tokens will be invalidated on restart.", exc
        )
        return secrets.token_urlsafe(64)


SECRET_KEY = _resolve_secret_key()

# Password hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength
    
    Returns:
        (is_valid, error_message) tuple
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isalpha() for c in password):
        return False, "Password must contain at least one letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    return True, ""


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Dictionary to encode in the token
        expires_delta: Optional expiration time delta
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode a JWT access token
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def check_permissions(user_permissions: list, required_permission: str) -> bool:
    """
    Check if user has required permission
    
    Args:
        user_permissions: List of permission strings
        required_permission: Permission to check for
    
    Returns:
        True if user has permission
    """
    # Superuser has all permissions
    if "superuser" in user_permissions:
        return True
    
    # Check for exact permission or wildcard
    if required_permission in user_permissions:
        return True
    
    # Check for wildcard permissions (e.g., "scripts.*" grants "scripts.read")
    permission_parts = required_permission.split('.')
    for i in range(len(permission_parts)):
        wildcard = '.'.join(permission_parts[:i+1]) + '.*'
        if wildcard in user_permissions:
            return True
    
    return False


# Default permissions structure.
# Permission names are "<resource>.<action>"; check_permissions() also honours
# "<resource>.*" wildcards and the "superuser" catch-all.
DEFAULT_PERMISSIONS = {
    "admin": [
        "superuser"
    ],
    "editor": [
        "scripts.read", "scripts.create", "scripts.update", "scripts.delete",
        "notes.read", "notes.create", "notes.update", "notes.delete",
        "tags.read", "tags.create", "tags.update", "tags.delete",
        "folders.read", "folders.update",
        "attachments.read", "attachments.upload", "attachments.delete",
        "roots.read", "roots.create", "roots.update", "roots.delete", "roots.scan",
        "search.read", "search.create", "search.update", "search.delete",
        "monitors.read", "monitors.create", "monitors.update", "monitors.delete",
        "schedules.read", "schedules.create", "schedules.update",
        "schedules.delete", "schedules.run",
        "notifications.read", "notifications.update",
        "incidents.read", "incidents.update",
    ],
    "viewer": [
        "scripts.read",
        "notes.read",
        "tags.read",
        "folders.read",
        "attachments.read",
        "roots.read",
        "search.read",
        "monitors.read",
        "schedules.read",
        "notifications.read",
        "incidents.read",
    ]
}


async def sync_role_permissions(db):
    """
    Refresh the built-in roles' permission sets.

    New resources (monitors, schedules, notifications) added permissions after
    the roles were first seeded; without this an existing install would leave
    editors and viewers unable to reach them.
    """
    import json

    for role_name, permissions in DEFAULT_PERMISSIONS.items():
        async with db.execute(
            "SELECT id, permissions FROM roles WHERE name = ?", (role_name,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            continue
        try:
            current = set(json.loads(row[1]))
        except (json.JSONDecodeError, TypeError):
            current = set()
        merged = sorted(current | set(permissions))
        if merged != sorted(current):
            await db.execute(
                "UPDATE roles SET permissions = ? WHERE id = ?",
                (json.dumps(merged), row[0]),
            )
    await db.commit()


async def init_default_roles(db):
    """Initialize default roles if they don't exist"""
    import json
    
    for role_name, permissions in DEFAULT_PERMISSIONS.items():
        # Check if role exists
        async with db.execute(
            "SELECT id FROM roles WHERE name = ?",
            (role_name,)
        ) as cursor:
            if await cursor.fetchone():
                continue
        
        # Create role
        permissions_json = json.dumps(permissions)
        await db.execute(
            "INSERT INTO roles (name, description, permissions) VALUES (?, ?, ?)",
            (role_name, f"Default {role_name} role", permissions_json)
        )
    
    await db.commit()


async def init_default_admin(db):
    """
    Create a bootstrap admin account if the installation has no users at all.

    Only reachable for installations that completed setup before the wizard
    existed. The password is randomly generated and logged once rather than
    being a well-known default, so an unattended upgrade never leaves an
    admin/admin account exposed on the network.
    """
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        count = (await cursor.fetchone())[0]
        if count > 0:
            return

    generated_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or secrets.token_urlsafe(16)
    hashed_password = get_password_hash(generated_password)
    cursor = await db.execute(
        """
        INSERT INTO users (username, email, full_name, hashed_password, is_active, is_superuser)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("admin", "admin@example.com", "Administrator", hashed_password, True, True)
    )
    user_id = cursor.lastrowid

    async with db.execute("SELECT id FROM roles WHERE name = ?", ("admin",)) as cursor:
        role_row = await cursor.fetchone()
        if role_row:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, role_row[0])
            )

    await db.commit()
    logger.warning(
        "No users existed; created a bootstrap admin account.\n"
        "    username: admin\n"
        "    password: %s\n"
        "Sign in and change this password immediately.",
        generated_password,
    )
