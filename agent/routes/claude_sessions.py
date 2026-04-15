"""
Phoenix v5 — Claude Session REST + WebSocket routes

Endpoints:
  POST   /claude-sessions          → create a session (+ optional worktree)
  GET    /claude-sessions          → list sessions (optional ?repo= filter)
  GET    /claude-sessions/{id}     → session detail + recent events
  DELETE /claude-sessions/{id}     → close session, cleanup worktree
  WS     /claude-sessions/{id}/ws  → interactive session stream
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

import db as _db
from claude_session import cleanup_session_worktree, manager

router = APIRouter(prefix="/claude-sessions", tags=["claude-sessions"])


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_session(
    repo: str = Query(..., description="owner/repo"),
    project_path: str = Query(..., description="Absolute path to project root"),
    clone_url: str = Query("", description="HTTPS clone URL for worktree setup (only used for claude_code mode)"),
    base_branch: str = Query("main", description="Base branch for the worktree"),
    mode: str = Query("claude_code", description="Terminal mode: claude_code | claude | copilot | openai"),
    model: str = Query("", description="Model name for API modes (ignored for claude_code)"),
    api_key: str = Query("", description="API key for the selected provider (stored locally, not logged)"),
) -> dict:
    """Create a new persistent Claude session.

    For claude_code mode, an isolated git worktree is optionally created from clone_url.
    For API modes (claude, openai, copilot), conversation history is maintained server-side.
    """
    session_id = str(uuid.uuid4())
    await manager.create(
        session_id=session_id,
        repo=repo,
        project_path=project_path,
        clone_url=clone_url or None,
        base_branch=base_branch,
        mode=mode,
        model=model,
        api_key=api_key,
    )
    session = await _db.get_claude_session(session_id)
    # Never return the api_key in responses.
    if session:
        session.pop("api_key", None)
    return {"session_id": session_id, "session": session}


@router.get("")
async def list_sessions(repo: str | None = Query(None)) -> dict:
    """List sessions, newest first. Filter by repo with ?repo=owner/repo."""
    sessions = await _db.list_claude_sessions(repo=repo)
    for s in sessions:
        s.pop("api_key", None)
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session(session_id: str, limit: int = Query(200)) -> dict:
    """Get session details and recent event history."""
    session = await _db.get_claude_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.pop("api_key", None)
    events = await _db.get_claude_session_events(session_id, limit=limit)
    return {"session": session, "events": events}


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """Close a session and remove its git worktree."""
    session = await _db.get_claude_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cleanup the isolated worktree if one was created.
    branch_name = (
        f"pnx/session-{session_id[:8]}"
        if session.get("worktree_path")
        else None
    )
    await cleanup_session_worktree(
        session["repo"],
        session.get("worktree_path"),
        branch_name,
    )
    await _db.delete_claude_session(session_id)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/{session_id}/ws")
async def session_websocket(websocket: WebSocket, session_id: str) -> None:
    """Interactive WebSocket for a Claude session.

    Client → server messages:
      {"type": "message", "content": "fix the auth bug"}

    Server → client messages (raw Claude CLI stream-json events + Phoenix status):
      {"type": "system",         "subtype": "init", "session_id": "...", ...}
      {"type": "assistant",      "message": {...}}
      {"type": "tool_use",       "name": "Read", "input": {...}}
      {"type": "tool_result",    "content": [...]}
      {"type": "result",         "subtype": "success", "result": "...", "usage": {...}}
      {"type": "user",           "content": "..."}   ← echoed user messages
      {"type": "error",          "message": "..."}
      {"type": "phoenix_status", "status": "running"|"idle"}
    """
    session = await _db.get_claude_session(session_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": f"Session {session_id} not found"})
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await manager.attach(session_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                content = data.get("content", "").strip()
                if content:
                    # Run the Claude invocation as a background task so the
                    # WebSocket receive loop stays responsive during processing.
                    import asyncio
                    asyncio.create_task(manager.send_message(session_id, content))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.detach(session_id, websocket)
