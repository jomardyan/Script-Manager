"""
Authentication and User Management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional, List
import aiosqlite
import json

from app.db.database import get_db
from app.services.auth import (
    verify_password, get_password_hash, create_access_token,
    decode_access_token, validate_password_strength
)
from app.models.schemas import UserRegister, UserUpdate

router = APIRouter()

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: aiosqlite.Connection = Depends(get_db)
) -> dict:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    # Get user from database
    async with db.execute(
        "SELECT id, username, email, full_name, is_active, is_superuser FROM users WHERE username = ?",
        (username,)
    ) as cursor:
        user = await cursor.fetchone()
        if not user:
            raise credentials_exception
        
        user_dict = dict(user)
    
    # Get user permissions
    async with db.execute(
        """
        SELECT r.permissions
        FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ?
        """,
        (user_dict['id'],)
    ) as cursor:
        roles = await cursor.fetchall()
        
        permissions = []
        for role in roles:
            role_perms = json.loads(role[0])
            permissions.extend(role_perms)
        
        user_dict['permissions'] = list(set(permissions))
    
    if not user_dict['is_active']:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return user_dict


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Login and get access token"""
    # Get user
    async with db.execute(
        "SELECT id, username, hashed_password, is_active FROM users WHERE username = ?",
        (form_data.username,)
    ) as cursor:
        user = await cursor.fetchone()
    
    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user[3]:  # is_active
        raise HTTPException(status_code=400, detail="Inactive user")
    
    # Create access token
    access_token = create_access_token(data={"sub": user[1]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user[1]
    }


@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    return current_user


@router.post("/register")
async def register_user(
    data: UserRegister,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Register a new user.
    Credentials are sent in the request body (never in the URL/query string).
    
    WARNING: Public self-registration is enabled. For production use,
    consider disabling this endpoint or implementing invitation-based registration.
    """
    username = data.username
    email = data.email
    password = data.password
    full_name = data.full_name
    # Validate password strength
    is_valid, error_msg = validate_password_strength(password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Check if username exists
    async with db.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already exists")
    
    # Check if email exists
    async with db.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")
    
    # Create user
    hashed_password = get_password_hash(password)
    cursor = await db.execute(
        """
        INSERT INTO users (username, email, full_name, hashed_password, is_active, is_superuser)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, email, full_name, hashed_password, True, False)
    )
    user_id = cursor.lastrowid
    
    # Assign default viewer role
    async with db.execute("SELECT id FROM roles WHERE name = ?", ("viewer",)) as cursor:
        role_row = await cursor.fetchone()
        if role_row:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, role_row[0])
            )
    
    await db.commit()
    
    return {
        "message": "User created successfully",
        "user_id": user_id,
        "username": username
    }


@router.put("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Change current user's password"""
    # Validate new password strength
    is_valid, error_msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Verify old password
    async with db.execute(
        "SELECT hashed_password FROM users WHERE id = ?",
        (current_user['id'],)
    ) as cursor:
        row = await cursor.fetchone()
        if not row or not verify_password(old_password, row[0]):
            raise HTTPException(status_code=400, detail="Incorrect password")
    
    # Update password
    new_hashed = get_password_hash(new_password)
    await db.execute(
        "UPDATE users SET hashed_password = ? WHERE id = ?",
        (new_hashed, current_user['id'])
    )
    await db.commit()
    
    return {"message": "Password changed successfully"}


# ── User management (admin) ───────────────────────────────────────────────────

def _is_admin(user: dict) -> bool:
    """Return True if the user has superuser privileges (via role or is_superuser flag)."""
    return bool(user.get("is_superuser")) or "superuser" in user.get("permissions", [])


@router.get("/users")
async def list_users(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all users with their assigned roles (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    async with db.execute(
        "SELECT id, username, email, full_name, is_active, is_superuser, created_at FROM users ORDER BY username"
    ) as cursor:
        users = await cursor.fetchall()
    result = []
    for u in users:
        user_dict = dict(u)
        async with db.execute(
            """
            SELECT r.id, r.name, r.description
            FROM roles r JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = ?
            """,
            (user_dict["id"],),
        ) as cur2:
            roles = await cur2.fetchall()
        user_dict["roles"] = [dict(r) for r in roles]
        result.append(user_dict)
    return result


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get a single user with roles (admin or self)."""
    if current_user["id"] != user_id and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    async with db.execute(
        "SELECT id, username, email, full_name, is_active, is_superuser, created_at FROM users WHERE id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    user_dict = dict(row)
    async with db.execute(
        """
        SELECT r.id, r.name, r.description
        FROM roles r JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ?
        """,
        (user_dict["id"],),
    ) as cur2:
        roles = await cur2.fetchall()
    user_dict["roles"] = [dict(r) for r in roles]
    return user_dict


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update a user's active status or role assignments (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

    if data.is_active is not None:
        await db.execute(
            "UPDATE users SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(data.is_active), user_id),
        )

    if data.role_ids is not None:
        await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        for rid in data.role_ids:
            await db.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, rid),
            )

    await db.commit()
    return await get_user(user_id, current_user, db)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete a user (admin only; cannot delete yourself)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()


@router.get("/roles")
async def list_roles(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List all roles (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    async with db.execute("SELECT id, name, description, permissions FROM roles ORDER BY name") as cursor:
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]
