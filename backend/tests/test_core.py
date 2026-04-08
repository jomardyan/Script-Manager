"""
Tests for Tags, Folder Roots, and core Script operations.
"""
import pytest


# ── Tags ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tags_empty(client):
    """Tags list should be empty on a fresh database."""
    resp = await client.get("/api/tags/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_tag(client):
    """Creating a tag should succeed."""
    resp = await client.post(
        "/api/tags/", json={"name": "automation", "color": "#3498db"}
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "automation"
    assert isinstance(data["id"], int)


@pytest.mark.asyncio
async def test_create_tag_duplicate(client):
    """Creating a duplicate tag should return 400."""
    await client.post("/api/tags/", json={"name": "unique_tag"})
    resp = await client.post("/api/tags/", json={"name": "unique_tag"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_tag(client):
    """Getting a tag by ID should return its data."""
    create = await client.post("/api/tags/", json={"name": "gettag"})
    tag_id = create.json()["id"]
    resp = await client.get(f"/api/tags/{tag_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "gettag"


@pytest.mark.asyncio
async def test_delete_tag(client):
    """Deleting a tag should return 200 with a success message."""
    create = await client.post("/api/tags/", json={"name": "deltag"})
    tag_id = create.json()["id"]
    resp = await client.delete(f"/api/tags/{tag_id}")
    assert resp.status_code == 200
    assert "deleted" in resp.json().get("message", "").lower()


# ── Folder Roots ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_folder_roots_empty(client):
    """Folder roots list should be empty on a fresh database."""
    resp = await client.get("/api/folder-roots/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_folder_root(client, tmp_path):
    """Creating a folder root should succeed."""
    resp = await client.post(
        "/api/folder-roots/",
        json={"path": str(tmp_path), "name": "Test Root"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "Test Root"
    assert isinstance(data["id"], int)


@pytest.mark.asyncio
async def test_get_folder_root(client, tmp_path):
    """Getting a folder root by ID should return its data."""
    create = await client.post(
        "/api/folder-roots/",
        json={"path": str(tmp_path), "name": "GetRoot"},
    )
    root_id = create.json()["id"]
    resp = await client.get(f"/api/folder-roots/{root_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetRoot"


@pytest.mark.asyncio
async def test_delete_folder_root(client, tmp_path):
    """Deleting a folder root should return 200 with a success message."""
    create = await client.post(
        "/api/folder-roots/",
        json={"path": str(tmp_path), "name": "DelRoot"},
    )
    root_id = create.json()["id"]
    resp = await client.delete(f"/api/folder-roots/{root_id}")
    assert resp.status_code == 200
    assert "deleted" in resp.json().get("message", "").lower()


# ── Saved Searches ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_saved_searches_empty(client):
    """Saved searches list should be empty on a fresh database."""
    resp = await client.get("/api/saved-searches/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_saved_search(client):
    """Creating a saved search should succeed."""
    resp = await client.post(
        "/api/saved-searches/",
        json={
            "name": "Python Scripts",
            "description": "All Python files",
            "query_params": {"languages": ["python"]},
            "is_pinned": True,
        },
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["name"] == "Python Scripts"
    assert data["is_pinned"] is True


@pytest.mark.asyncio
async def test_delete_saved_search(client):
    """Deleting a saved search should return 200 with a success message."""
    create = await client.post(
        "/api/saved-searches/",
        json={"name": "To Delete Search", "query_params": {}},
    )
    search_id = create.json()["id"]
    resp = await client.delete(f"/api/saved-searches/{search_id}")
    assert resp.status_code == 200
    assert "deleted" in resp.json().get("message", "").lower()
