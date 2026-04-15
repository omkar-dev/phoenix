"""
Global SSE broadcast — fan-out to all connected /events clients.

Usage:
    q = await subscribe()          # called by the SSE endpoint on connect
    unsubscribe(q)                 # called on disconnect
    await broadcast({"type": …})  # called anywhere to push an event
"""

import asyncio
import json
from typing import Any

_clients: set[asyncio.Queue] = set()


async def subscribe() -> asyncio.Queue:
    """Register a new SSE client and return its dedicated queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _clients.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """Remove a client queue (called on disconnect or error)."""
    _clients.discard(q)


async def broadcast(event: dict[str, Any]) -> None:
    """Fan-out a JSON-serialisable event to every connected SSE client.

    Clients whose queues are full (slow readers) are silently dropped to
    prevent a lagging browser from blocking everyone else.
    """
    if not _clients:
        return
    msg = json.dumps(event)
    dead: set[asyncio.Queue] = set()
    for q in list(_clients):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.add(q)
    _clients -= dead
