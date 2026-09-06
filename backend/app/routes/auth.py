"""
Authentication and User Management API endpoints
"""
import os
from datetime import timedelta
from typing import List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.db.database import get_db
from app.models.schemas import PasswordChange, UserRegister, UserUpdate
from app.routes.deps import (
    get_current_user, get_optional_user, is_admin, oauth2_scheme, require_admin,
)
from app.services.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, get_password_hash,
    validate_password_strength, verify_password,
)

router = APIRouter()

admin_only = Depends(require_admin())


def self_registration_enabled() -> bool:
    """
    Whether anonymous users may create their own account.

    Off by default: an internet-reachable instance should not let strangers
    create accounts. Administrators can always create users from the Team page.
    """
    return os.getenv("ALLOW_SELF_REGISTRATION", "false").strip().lower() in ("1", "true", "yes", "on")


async def _count_active_admins(db: aiosqlite.Connection, exclude_user_id: Optional[int] = None) -> int:
    """Count active users that still hold superuser privileges."""
    query = """
        SELECT COUNT(DISTINCT u.id)
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON r.id = ur.role_id
        WHERE u.is_active = 1
          AND (u.is_superuser = 1 OR r.permissions LIKE '%superuser%')
    """
    params: tuple = ()
    if exclude_user_id is not None:
        query += " AND u.id != ?"
        params = (exclude_user_id,)
    async with db.execute(query, params) as cursor:
        return (await cursor.fetchone())[0]


async def _load_user_with_roles(db: aiosqlite.Connection, user_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT id, username, email, full_name, is_active, is_superuser, last_login_at, created_at "
        "FROM users WHERE id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    user = dict(row)
    async with db.execute(
        """
        SELECT r.id, r.name, r.description
        FROM roles r JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ?
        ORDER BY r.name
        """,
        (user_id,),
    ) as cursor:
        user["roles"] = [dict(r) for r in await cursor.fetchall()]
    return user


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Login and get access token"""
    async with db.execute(
        "SELECT id, username, hashed_password, is_active FROM users WHERE username = ?",
        (form_data.username,),
    ) as cursor:
        user = await cursor.fetchone()

    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user[3]:  # is_active
        raise HTTPException(status_code=403, detail="This account has been deactivated")

    await db.execute(
        "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user[0],)
    )
    await db.commit()

    access_token = create_access_token(
        data={"sub": user[1]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user[1],
        # Lets the client refresh or warn before the session silently expires.
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user info, including the flattened permission set."""
    return current_user


@router.get("/config")
async def auth_config(db: aiosqlite.Connection = Depends(get_db)):
    """
    Public description of how authentication is configured.

    The sign-in screen uses this to decide whether to offer self-registration
    and to tell a brand-new install that no accounts exist yet.
    """
    from app.routes.deps import auth_required

    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        user_count = (await cursor.fetchone())[0]
    return {
        "auth_required": auth_required(),
        "self_registration_enabled": self_registration_enabled(),
        "has_users": user_count > 0,
    }


@router.post("/register", status_code=201)
async def register_user(
    data: UserRegister,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: Optional[dict] = Depends(get_optional_user),
):
    """
    Create a user account.

    Administrators can always create accounts. Anonymous self-registration is
    only permitted when ALLOW_SELF_REGISTRATION is enabled, so a public
    deployment does not hand out accounts by default.
    """
    if not is_admin(current_user) and not self_registration_enabled():
        raise HTTPException(
            status_code=403,
            detail="Self-registration is disabled. Ask an administrator to create your account.",
        )

    username = data.username.strip()
    email = data.email.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    is_valid, error_msg = validate_password_strength(data.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    async with db.execute("SELECT id FROM users WHERE username = ?", (username,)) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already exists")

    async with db.execute("SELECT id FROM users WHERE email = ?", (email,)) as cursor:
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")

    # Only an administrator may pick the new account's roles; everyone else
    # gets the read-only viewer role.
    requested_role_ids = data.role_ids if (data.role_ids and is_admin(current_user)) else None

    hashed_password = get_password_hash(data.password)
    cursor = await db.execute(
        """
        INSERT INTO users (username, email, full_name, hashed_password, is_active, is_superuser)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, email, data.full_name, hashed_password, True, False),
    )
    user_id = cursor.lastrowid

    if requested_role_ids:
        for role_id in requested_role_ids:
            await db.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, role_id),
            )
    else:
        async with db.execute("SELECT id FROM roles WHERE name = ?", ("viewer",)) as cursor:
            role_row = await cursor.fetchone()
            if role_row:
                await db.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                    (user_id, role_row[0]),
                )

    await db.commit()

    return {
        "message": "User created successfully",
        "user_id": user_id,
        "username": username,
    }


@router.put("/change-password")
async def change_password(
    data: PasswordChange,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Change the signed-in user's password.

    Credentials are read from the request body; sending them as query
    parameters (as this endpoint previously required) leaks them into access
    logs, browser history and proxy caches.
    """
    is_valid, error_msg = validate_password_strength(data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    if data.new_password == data.old_password:
        raise HTTPException(
            status_code=400, detail="The new password must differ from the current one"
        )

    async with db.execute(
        "SELECT hashed_password FROM users WHERE id = ?", (current_user["id"],)
    ) as cursor:
        row = await cursor.fetchone()
        if not row or not verify_password(data.old_password, row[0]):
            raise HTTPException(status_code=400, detail="Incorrect password")

    new_hashed = get_password_hash(data.new_password)
    await db.execute(
        "UPDATE users SET hashed_password = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_hashed, current_user["id"]),
    )
    await db.commit()

    return {"message": "Password changed successfully"}


# ── User management (admin) ───────────────────────────────────────────────────

@router.get("/users", dependencies=[admin_only])
async def list_users(db: aiosqlite.Connection = Depends(get_db)):
    """List all users with their assigned roles (admin only)."""
    async with db.execute(
        "SELECT id, username, email, full_name, is_active, is_superuser, last_login_at, created_at "
        "FROM users ORDER BY username"
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
            ORDER BY r.name
            """,
            (user_dict["id"],),
        ) as cur2:
            user_dict["roles"] = [dict(r) for r in await cur2.fetchall()]
        result.append(user_dict)
    return result


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get a single user with roles (admin or self)."""
    if current_user["id"] != user_id and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    user = await _load_user_with_roles(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}", dependencies=[admin_only])
async def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update a user's profile, active status or role assignments (admin only)."""
    async with db.execute(
        "SELECT id, is_superuser FROM users WHERE id = ?", (user_id,)
    ) as cursor:
        target = await cursor.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

    # Losing the last administrator would lock everyone out of user management,
    # so a change that would strip the final admin is rejected up front.
    if await _count_active_admins(db, exclude_user_id=user_id) == 0:
        current = await _admin_state(db, user_id)
        if current["is_admin"]:
            will_be_active = data.is_active if data.is_active is not None else current["is_active"]
            will_be_super = (
                data.is_superuser if data.is_superuser is not None else current["is_superuser"]
            )
            will_have_admin_role = (
                await _role_ids_include_admin(db, data.role_ids)
                if data.role_ids is not None else current["has_admin_role"]
            )
            if not (will_be_active and (will_be_super or will_have_admin_role)):
                raise HTTPException(
                    status_code=400,
                    detail="This is the last administrator account; "
                           "it cannot be demoted or deactivated.",
                )

    if data.full_name is not None:
        await db.execute(
            "UPDATE users SET full_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (data.full_name, user_id),
        )
    if data.email is not None:
        async with db.execute(
            "SELECT id FROM users WHERE email = ? AND id != ?", (data.email, user_id)
        ) as cursor:
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Email already exists")
        await db.execute(
            "UPDATE users SET email = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (data.email, user_id),
        )
    if data.is_active is not None:
        await db.execute(
            "UPDATE users SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(data.is_active), user_id),
        )
    if data.is_superuser is not None:
        await db.execute(
            "UPDATE users SET is_superuser = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(data.is_superuser), user_id),
        )

    if data.role_ids is not None:
        async with db.execute("SELECT id FROM roles") as cursor:
            valid_role_ids = {row[0] for row in await cursor.fetchall()}
        unknown = sorted(set(data.role_ids) - valid_role_ids)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown role id(s): {', '.join(str(r) for r in unknown)}",
            )
        await db.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        for rid in data.role_ids:
            await db.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, rid),
            )

    if data.password is not None:
        is_valid, error_msg = validate_password_strength(data.password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        await db.execute(
            "UPDATE users SET hashed_password = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (get_password_hash(data.password), user_id),
        )

    await db.commit()
    return await _load_user_with_roles(db, user_id)


async def _admin_state(db: aiosqlite.Connection, user_id: int) -> dict:
    """Describe how a user currently qualifies (or not) as an administrator."""
    async with db.execute(
        "SELECT is_active, is_superuser FROM users WHERE id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {"is_active": False, "is_superuser": False, "has_admin_role": False, "is_admin": False}
    async with db.execute(
        """
        SELECT 1 FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = ? AND r.permissions LIKE '%superuser%'
        """,
        (user_id,),
    ) as cursor:
        has_admin_role = await cursor.fetchone() is not None
    is_active = bool(row[0])
    is_superuser = bool(row[1])
    return {
        "is_active": is_active,
        "is_superuser": is_superuser,
        "has_admin_role": has_admin_role,
        "is_admin": is_active and (is_superuser or has_admin_role),
    }


async def _role_ids_include_admin(db: aiosqlite.Connection, role_ids: Optional[List[int]]) -> bool:
    if not role_ids:
        return False
    placeholders = ",".join("?" * len(role_ids))
    async with db.execute(
        f"SELECT 1 FROM roles WHERE id IN ({placeholders}) AND permissions LIKE '%superuser%'",
        tuple(role_ids),
    ) as cursor:
        return await cursor.fetchone() is not None


@router.delete("/users/{user_id}", status_code=204, dependencies=[admin_only])
async def delete_user(
    user_id: int,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete a user (admin only; cannot delete yourself or the last admin)."""
    if current_user and user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
    if await _count_active_admins(db, exclude_user_id=user_id) == 0:
        raise HTTPException(
            status_code=400,
            detail="This is the last administrator account; it cannot be deleted.",
        )
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()


@router.get("/roles", dependencies=[admin_only])
async def list_roles(db: aiosqlite.Connection = Depends(get_db)):
    """List all roles (admin only). Permissions are returned as a JSON array."""
    import json

    async with db.execute(
        "SELECT id, name, description, permissions FROM roles ORDER BY name"
    ) as cursor:
        rows = await cursor.fetchall()
    roles = []
    for row in rows:
        role = dict(row)
        try:
            role["permissions"] = json.loads(role["permissions"])
        except (json.JSONDecodeError, TypeError):
            role["permissions"] = []
        roles.append(role)
    return roles
