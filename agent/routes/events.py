"""
GET /events — global SSE stream for multiplayer state sync.

All connected browsers subscribe here and receive broadcast events
(run_started, run_updated, run_cancelled, card_moved) in real time.
"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

import broadcast as _broadcast
from registry import _runs

router = APIRouter()


def _snapshot() -> list[dict]:
    """Serialisable snapshot of all in-flight runs (no agent object)."""
    return [
        {
            "runId": s.run_id,
            "issueNumber": s.agent.request.issue_number,
            "repo": s.agent.request.repo_full_name,
            "done": s.task.done(),
        }
        for s in _runs.values()
    ]


@router.get("/events")
async def global_events(request: Request) -> StreamingResponse:
    """SSE endpoint — subscribe to real-time board state changes."""
    q = await _broadcast.subscribe()

    async def stream():
        try:
            # Send a snapshot immediately so a fresh tab syncs active runs
            yield f"data: {json.dumps({'type': 'snapshot', 'runs': _snapshot()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            _broadcast.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
