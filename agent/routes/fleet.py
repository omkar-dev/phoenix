"""
Phoenix v5 — Fleet Dashboard API (Phase 5)

GET /fleet/status  — snapshot of all active lifecycle rows + agent status
GET /fleet/events  — SSE stream filtered to fleet-relevant events
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

import broadcast as _broadcast
import db as _db
from registry import _runs

router = APIRouter()

FLEET_EVENTS = {
    "lifecycle_updated",
    "run_started",
    "run_updated",
    "run_cancelled",
    "review_requested_changes",
    "ci_retry_limit_reached",
    "auto_merge_failed",
}


def _agent_status(run_id: str) -> str:
    """Return 'running', 'done', or 'idle' based on the in-memory run registry."""
    state = _runs.get(run_id)
    if state is None:
        return "idle"
    return "done" if state.task.done() else "running"


async def _fleet_snapshot() -> list[dict]:
    """Return all active lifecycle rows enriched with agent status."""
    rows = await _db.list_active_lifecycles(max_age_hours=72)
    result = []
    for row in rows:
        result.append({
            "run_id": row["run_id"],
            "repo": row["repo"],
            "issue_number": row["issue_number"],
            "pr_number": row.get("pr_number"),
            "pr_url": row.get("pr_url"),
            "branch": row.get("branch_name"),
            "lifecycle_state": row["state"],
            "ci_conclusion": row.get("ci_conclusion"),
            "review_decision": row.get("review_decision"),
            "agent_status": _agent_status(row["run_id"]),
            "updated_at": row["updated_at"],
        })
    return result


@router.get("/fleet/status")
async def fleet_status() -> list[dict]:
    """Return current fleet status snapshot."""
    return await _fleet_snapshot()


@router.get("/fleet/events")
async def fleet_events(request: Request) -> StreamingResponse:
    """SSE stream of fleet-relevant events only."""
    q = await _broadcast.subscribe()

    async def stream():
        try:
            # Send full snapshot immediately on connect
            snapshot = await _fleet_snapshot()
            yield f"data: {json.dumps({'type': 'fleet_snapshot', 'items': snapshot})}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    try:
                        event = json.loads(msg)
                        if event.get("type") in FLEET_EVENTS:
                            yield f"data: {msg}\n\n"
                    except (json.JSONDecodeError, TypeError):
                        pass
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            _broadcast.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
