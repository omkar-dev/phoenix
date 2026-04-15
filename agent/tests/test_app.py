"""Smoke tests for the FastAPI app — health endpoint and basic routing."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Provide required env vars before importing the app
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import db
from app import _on_shutdown, app
from registry import RunState, _runs


@pytest.fixture(autouse=True)
def patch_db(tmp_path, monkeypatch):
    """Use a temp DB for every test so tests are fully isolated."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "version" in data
    assert "active_runs" in data


async def test_repos_empty(client):
    resp = await client.get("/repos")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_repos_post_and_get(client):
    resp = await client.post("/repos", json={"full_name": "owner/repo"})
    assert resp.status_code == 200

    resp = await client.get("/repos")
    assert any(r["full_name"] == "owner/repo" for r in resp.json())


async def test_repos_delete(client):
    await client.post("/repos", json={"full_name": "owner/repo"})
    resp = await client.delete("/repos/owner/repo")
    assert resp.status_code == 200

    resp = await client.get("/repos")
    assert not any(r["full_name"] == "owner/repo" for r in resp.json())


async def test_team_assignment_no_teams(client):
    resp = await client.post("/team-assignment", json={
        "repo": "owner/repo",
        "issue_number": 1,
        "issue_title": "Test issue",
        "to_column": "todo",
        "teams": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_manual"] is True
    assert data["team_id"] is None


async def test_team_assignment_no_api_key(client, monkeypatch):
    monkeypatch.setattr("routes.movements.ANTHROPIC_API_KEY", "")
    resp = await client.post("/team-assignment", json={
        "repo": "owner/repo",
        "issue_number": 2,
        "issue_title": "Test issue",
        "to_column": "todo",
        "teams": [{"id": "fullstack", "name": "Full Stack"}],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_manual"] is True


async def test_team_assignment_ai_success(client, monkeypatch):
    import json as _json
    from unittest.mock import AsyncMock, MagicMock

    mock_content = MagicMock()
    mock_content.text = _json.dumps({
        "team_id": "fullstack",
        "confidence": 0.9,
        "reasoning": "Full Stack team handles authentication issues.",
    })
    mock_message = MagicMock()
    mock_message.content = [mock_content]

    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = AsyncMock(return_value=mock_message)

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", MagicMock(return_value=mock_client_instance))

    resp = await client.post("/team-assignment", json={
        "repo": "owner/repo",
        "issue_number": 3,
        "issue_title": "Add OAuth2 login",
        "issue_body": "Implement GitHub OAuth2 for authentication.",
        "to_column": "todo",
        "teams": [
            {"id": "fullstack", "name": "Full Stack"},
            {"id": "backend", "name": "Backend"},
        ],
        "llm_api_key": "test-key",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == "fullstack"
    assert data["needs_manual"] is False
    assert data["confidence"] == 0.9


async def test_team_assignment_ai_low_confidence(client, monkeypatch):
    import json as _json
    from unittest.mock import AsyncMock, MagicMock

    mock_content = MagicMock()
    mock_content.text = _json.dumps({
        "team_id": "backend",
        "confidence": 0.3,
        "reasoning": "Unclear which team should handle this.",
    })
    mock_message = MagicMock()
    mock_message.content = [mock_content]

    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = AsyncMock(return_value=mock_message)

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", MagicMock(return_value=mock_client_instance))

    resp = await client.post("/team-assignment", json={
        "repo": "owner/repo",
        "issue_number": 4,
        "issue_title": "Fix something",
        "to_column": "todo",
        "teams": [{"id": "backend", "name": "Backend"}],
        "llm_api_key": "test-key",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_manual"] is True
    assert data["team_id"] is None


async def test_movements_empty(client):
    resp = await client.get("/movements")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_movements_log(client):
    resp = await client.post("/movements", json={
        "repo": "owner/repo",
        "issue_number": 10,
        "from_column": "triage",
        "to_column": "todo",
    })
    assert resp.status_code == 200

    resp = await client.get("/movements?repo=owner/repo")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["issue_number"] == 10


async def test_movements_log_with_actor(client):
    resp = await client.post("/movements", json={
        "repo": "owner/repo",
        "issue_number": 11,
        "from_column": "triage",
        "to_column": "in_progress",
        "actor": "octocat",
    })
    assert resp.status_code == 200
    assert resp.status_code == 204
    resp = await client.get("/movements?repo=owner/repo")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["actor"] == "octocat"


async def test_movements_log_without_actor_is_null(client):
    resp = await client.post("/movements", json={
        "repo": "owner/repo",
        "issue_number": 12,
        "from_column": "todo",
        "to_column": "in_progress",
    })
    assert resp.status_code == 200

    assert resp.status_code == 204
    data = resp.json()
    assert data[0]["actor"] is None


# ── Graceful shutdown ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def cleanup_runs():
    """Remove any test entries from the shared run registry after each test."""
    yield
    _runs.clear()


async def test_shutdown_cancels_active_tasks():
    """_on_shutdown cancels in-flight tasks and empties the run registry.

    MagicMock is used for the agent stub because creating a real ImplementerAgent
    would require live GitHub/OpenHands credentials and a real git repository.
    The shutdown handler only calls agent._cleanup_worktree(), so a stub is the
    minimal interface we need to verify coordination without I/O side-effects.
    """
    agent = MagicMock()
    agent._cleanup_worktree = AsyncMock()

    async def _never_finish():
        await asyncio.sleep(1000)

    task = asyncio.create_task(_never_finish())
    _runs["shutdown-test"] = RunState(run_id="shutdown-test", agent=agent, task=task)

    await _on_shutdown()

    assert "shutdown-test" not in _runs
    assert task.cancelled()
    agent._cleanup_worktree.assert_awaited_once()


async def test_shutdown_noop_when_no_active_runs():
    """_on_shutdown exits immediately when there are no active runs."""
    assert not _runs
    await _on_shutdown()  # must not raise


async def test_shutdown_clears_refine_queues():
    """_on_shutdown clears the refine SSE queue map."""
    from routes.refine import _refine_queues

    _refine_queues["test-refine-id"] = asyncio.Queue()
    await _on_shutdown()
    assert not _refine_queues


async def test_cancel_run_schedules_worktree_cleanup(client):
    """DELETE /runs/{run_id} cancels the task and schedules worktree cleanup.

    MagicMock is used for the same reason as in test_shutdown_cancels_active_tasks:
    real ImplementerAgent instances require live credentials and git operations.
    """
    agent = MagicMock()
    agent._cleanup_worktree = AsyncMock()

    async def _never_finish():
        await asyncio.sleep(1000)

    task = asyncio.create_task(_never_finish())
    _runs["cancel-test"] = RunState(run_id="cancel-test", agent=agent, task=task)

    resp = await client.delete("/runs/cancel-test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "cancel-test" not in _runs

    # Yield to the event loop so the background cleanup task can run.
    await asyncio.sleep(0)
    agent._cleanup_worktree.assert_awaited_once()
