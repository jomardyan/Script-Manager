"""
Shared FastAPI dependencies for authentication and authorization.

The application ships a full RBAC model (roles, permissions, wildcards) but
before this module existed almost no endpoint consulted it, so every route was
reachable anonymously. `require_permission` turns that model into an actual
gate that routers can attach with one line.

Enforcement can be disabled with ``REQUIRE_AUTH=false`` for local development
and for the test suite; it is on by default so a deployment is never
accidentally left open.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import aiosqlite
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.db.database import get_db
from app.services.auth import check_permissions, decode_access_token

# tokenUrl is relative to the app root; auto_error=False lets us return a
# clearer message than "Not authenticated" and lets anonymous access work when
# enforcement is switched off.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def auth_required() -> bool:
    """Whether API authorization is enforced (read at call time so tests can flip it)."""
    return os.getenv("REQUIRE_AUTH", "true").strip().lower() not in ("0", "false", "no", "off")


async def load_user(db: aiosqlite.Connection, username: str) -> Optional[dict]:
    """Load a user plus their flattened permission set, or None if unknown."""
    async with db.execute(
        "SELECT id, username, email, full_name, is_active, is_superuser, created_at "
        "FROM users WHERE username = ?",
        (username,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None

    user = dict(row)
    async with db.execute(
        """
        SELECT r.permissions
        FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ?
        """,
        (user["id"],),
    ) as cursor:
        roles = await cursor.fetchall()

    permissions: set = set()
    for role in roles:
        try:
            permissions.update(json.loads(role[0]))
        except (json.JSONDecodeError, TypeError):
            continue
    if user.get("is_superuser"):
        permissions.add("superuser")
    user["permissions"] = sorted(permissions)
    return user


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """Resolve the authenticated user, raising 401 when the token is absent or bad."""
    if not token:
        raise CREDENTIALS_EXCEPTION

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise CREDENTIALS_EXCEPTION

    user = await load_user(db, username)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="This account has been deactivated")
    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: aiosqlite.Connection = Depends(get_db),
) -> Optional[dict]:
    """
    Resolve the current user when a valid token is present, else None.

    Used for audit attribution on endpoints that stay reachable without auth.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = await load_user(db, username)
    if user is None or not user["is_active"]:
        return None
    return user


def require_permission(permission: str):
    """
    Build a dependency that requires `permission` (or a wildcard covering it).

    Use as a route/router dependency:

        router = APIRouter(dependencies=[Depends(require_permission("tags.read"))])

    When ``REQUIRE_AUTH`` is disabled the dependency resolves to None and the
    endpoint stays open, which keeps single-user local setups frictionless.
    """

    async def dependency(
        request: Request,
        token: Optional[str] = Depends(oauth2_scheme),
        db: aiosqlite.Connection = Depends(get_db),
    ) -> Optional[dict]:
        if not auth_required():
            # Still attach the user when a token happens to be supplied so that
            # audit trails record an actor.
            return await get_optional_user(token, db)

        user = await get_current_user(token, db)
        if not check_permissions(user["permissions"], permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        request.state.user = user
        return user

    return dependency


def require_admin():
    """Dependency requiring superuser privileges."""

    async def dependency(
        token: Optional[str] = Depends(oauth2_scheme),
        db: aiosqlite.Connection = Depends(get_db),
    ) -> Optional[dict]:
        if not auth_required():
            return await get_optional_user(token, db)
        user = await get_current_user(token, db)
        if not is_admin(user):
            raise HTTPException(status_code=403, detail="Admin access required")
        return user

    return dependency


def is_admin(user: Optional[dict]) -> bool:
    """True when the user has superuser privileges via flag or role."""
    if not user:
        return False
    return bool(user.get("is_superuser")) or "superuser" in user.get("permissions", [])


def actor_name(user: Optional[dict]) -> Optional[str]:
    """Username to record in audit trails, or None for anonymous requests."""
    return user.get("username") if user else None
