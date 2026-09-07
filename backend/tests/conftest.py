"""
Shared pytest fixtures for Script Manager backend tests.
"""
import os
import tempfile
import pytest
import pytest_asyncio
import aiosqlite
from httpx import AsyncClient, ASGITransport

# Insert the backend root onto sys.path so imports resolve correctly.
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# The background scheduler would fire real subprocesses against the per-test
# database, so it stays off for the whole suite.
os.environ.setdefault("ENABLE_SCHEDULER", "false")

import app.db.database as _db_mod
# Route modules that imported DB_PATH using `from app.db.database import DB_PATH`
# hold a local string reference (not a module attribute lookup), so patching
# _db_mod.DB_PATH alone won't affect them — they must be patched separately to
# use the per-test database.
import app.routes.schedules as _sched_mod
import app.routes.folder_roots as _fr_mod
import app.routes.watch as _watch_mod
from main import app as _app

# All modules that carry their own DB_PATH reference alongside _db_mod
_DB_PATH_MODULES = (_sched_mod, _fr_mod, _watch_mod)

ADMIN_USERNAME = "testadmin"
ADMIN_PASSWORD = "TestPass123!"


@pytest_asyncio.fixture
async def app():
    """Provide the FastAPI app with a fresh per-test SQLite database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    # --- patch DB_PATH in every module that holds a direct reference ----------
    original_db_path = _db_mod.DB_PATH
    _db_mod.DB_PATH = db_path
    for mod in _DB_PATH_MODULES:
        mod.DB_PATH = db_path

    await _db_mod.init_db()

    # Seed default roles into the test database
    from app.services.auth import init_default_roles, sync_role_permissions
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await _db_mod.apply_connection_pragmas(db)
        await init_default_roles(db)
        await sync_role_permissions(db)

    # Override get_db to always use our temp database
    async def _override_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await _db_mod.apply_connection_pragmas(db)
            yield db

    # Snapshot and restore only the specific override we add so we don't
    # disturb any other overrides that might be registered on the shared app.
    _prior_override = _app.dependency_overrides.get(_db_mod.get_db)
    _app.dependency_overrides[_db_mod.get_db] = _override_get_db

    yield _app

    # Restore the get_db override to exactly what it was before this fixture
    if _prior_override is None:
        _app.dependency_overrides.pop(_db_mod.get_db, None)
    else:
        _app.dependency_overrides[_db_mod.get_db] = _prior_override

    # Restore DB_PATH in all patched modules
    _db_mod.DB_PATH = original_db_path
    for mod in _DB_PATH_MODULES:
        mod.DB_PATH = original_db_path

    os.unlink(db_path)


@pytest_asyncio.fixture
async def anon_client(app):
    """
    Async HTTP client with no credentials.

    Use this for endpoints that must work before anyone can sign in (the setup
    wizard) and for asserting that protected endpoints reject anonymous callers.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def _bootstrap_admin(ac: AsyncClient) -> str:
    """Complete setup so an admin account exists, then return its access token."""
    resp = await ac.post(
        "/api/setup/complete",
        json={
            "mode": "development",
            "database": {"type": "sqlite"},
            "admin": {
                "username": ADMIN_USERNAME,
                "email": "testadmin@example.com",
                "password": ADMIN_PASSWORD,
            },
        },
    )
    assert resp.status_code in (200, 201, 409), resp.text

    login = await ac.post(
        "/api/auth/login",
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


@pytest_asyncio.fixture
async def client(app):
    """
    Default client: authenticated as an administrator.

    The API enforces RBAC on every resource, so the common case for a test is
    an authenticated caller. Tests that need an anonymous caller use
    `anon_client`.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        token = await _bootstrap_admin(ac)
        ac.headers.update({"Authorization": f"Bearer {token}"})
        yield ac


@pytest_asyncio.fixture
async def auth_client(client):
    """Alias kept for tests that explicitly ask for an authenticated client."""
    return client


@pytest_asyncio.fixture
async def viewer_client(app, client):
    """A second client signed in as a read-only viewer, for RBAC assertions."""
    created = await client.post(
        "/api/auth/register",
        json={
            "username": "testviewer",
            "email": "testviewer@example.com",
            "password": "ViewerPass123!",
        },
    )
    assert created.status_code in (200, 201), created.text

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        login = await ac.post(
            "/api/auth/login",
            data={"username": "testviewer", "password": "ViewerPass123!"},
        )
        assert login.status_code == 200, login.text
        ac.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
        yield ac
