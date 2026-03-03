"""
Shared pytest fixtures for Script Manager backend tests.
"""
import os
import tempfile
import pytest
import pytest_asyncio
import aiosqlite
from httpx import AsyncClient, ASGITransport

# Import the single app instance (module-level import keeps it stable)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app.db.database as _db_mod
from main import app as _app


@pytest_asyncio.fixture
async def app():
    """Provide the FastAPI app with a fresh per-test SQLite database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    # Patch the module-level DB_PATH so init_db writes to our temp file
    original_db_path = _db_mod.DB_PATH
    _db_mod.DB_PATH = db_path

    await _db_mod.init_db()

    # Seed default roles into the test database
    from app.services.auth import init_default_roles
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await init_default_roles(db)

    # Override get_db to always use our temp database
    async def _override_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    _app.dependency_overrides[_db_mod.get_db] = _override_get_db

    yield _app

    _app.dependency_overrides.clear()
    _db_mod.DB_PATH = original_db_path
    os.unlink(db_path)


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client bound to the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client):
    """Client with a valid admin JWT token pre-attached."""
    # Complete setup first so an admin account exists
    resp = await client.post(
        "/api/setup/complete",
        json={
            "mode": "development",
            "database": {"type": "sqlite"},
            "admin": {
                "username": "testadmin",
                "email": "testadmin@example.com",
                "password": "TestPass123!",
            },
        },
    )
    assert resp.status_code in (200, 201, 409), resp.text

    login = await client.post(
        "/api/auth/login",
        data={"username": "testadmin", "password": "TestPass123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
