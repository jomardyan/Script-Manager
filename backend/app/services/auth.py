"""
Authentication service
Handles JWT tokens, password hashing, and user authentication
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
import os

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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


# Default permissions structure
DEFAULT_PERMISSIONS = {
    "admin": [
        "superuser"
    ],
    "editor": [
        "scripts.read",
        "scripts.create",
        "scripts.update",
        "scripts.delete",
        "notes.read",
        "notes.create",
        "notes.update",
        "notes.delete",
        "tags.read",
        "tags.create",
        "tags.update",
        "tags.delete",
        "folders.read",
        "folders.update",
        "attachments.read",
        "attachments.upload",
        "attachments.delete"
    ],
    "viewer": [
        "scripts.read",
        "notes.read",
        "tags.read",
        "folders.read",
        "attachments.read"
    ]
}


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
    """Initialize default admin user if no users exist"""
    # Check if any users exist
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        count = (await cursor.fetchone())[0]
        if count > 0:
            return
    
    # Create default admin user
    hashed_password = get_password_hash("admin")
    cursor = await db.execute(
        """
        INSERT INTO users (username, email, full_name, hashed_password, is_active, is_superuser)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("admin", "admin@example.com", "Administrator", hashed_password, True, True)
    )
    user_id = cursor.lastrowid
    
    # Assign admin role
    async with db.execute("SELECT id FROM roles WHERE name = ?", ("admin",)) as cursor:
        role_row = await cursor.fetchone()
        if role_row:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, role_row[0])
            )
    
    await db.commit()
    print("Created default admin user (username: admin, password: admin)")
    print("⚠️  IMPORTANT: Change the default admin password immediately!")
