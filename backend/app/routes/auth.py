"""
Authentication and User Management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional
import aiosqlite
import json

from app.db.database import get_db
from app.services.auth import (
    verify_password, get_password_hash, create_access_token,
    decode_access_token, check_permissions
)

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
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Register a new user"""
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
