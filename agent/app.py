import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import db as _db
from config import CORS_ORIGINS
from routes import claude_sessions, events, movements, notes, refine, repos, runs, worktree

app = FastAPI(title="Phoenix ImplementerAgent", version="5.0.0")


@app.on_event("startup")
async def _on_startup() -> None:
    """Initialise SQLite DB and clean up stale worktrees from previous crashes."""
    await _db.init_db()
    # Clean up stale *run* worktrees (pnx-<8hex>) but NOT session worktrees
    # (pnx-session-*) — sessions must persist between page reloads for --resume.
    tmp = Path(tempfile.gettempdir())
    for d in tmp.glob("pnx-*"):
        if d.is_dir() and not d.name.startswith("pnx-session-"):
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Cancel every active agent run and wait for cleanup before the process exits.

    Steps:
      1. Clear the refine-stream queue map so SSE generators stop emitting.
      2. Cancel all in-flight agent asyncio tasks.
      3. Wait up to 30 s for tasks to acknowledge cancellation.
      4. Call each agent's worktree cleanup (best-effort; errors are silenced).
      5. Clear the run registry so GC can collect everything.
    """
    from registry import _runs
    from routes.refine import _refine_queues

    _refine_queues.clear()

    if not _runs:
        return

    # Step 2: cancel every task that is still running.
    for state in list(_runs.values()):
        if not state.task.done():
            state.task.cancel()

    # Step 3: wait for cancellations to propagate (ignore already-done tasks).
    pending = [state.task for state in _runs.values() if not state.task.done()]
    if pending:
        await asyncio.wait(pending, timeout=30.0)

    # Step 4: remove worktrees (fire each cleanup sequentially; errors are silenced).
    for state in list(_runs.values()):
        try:
            await state.agent._cleanup_worktree()
        except Exception:
            pass

    # Step 5: release all references.
    _runs.clear()


_allow_origins = (
    [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    if CORS_ORIGINS
    else []
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins if _allow_origins else ["*"],
    allow_origin_regex=None if _allow_origins else r"http://localhost:\d+",
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health() -> dict:
    from registry import _runs
    return {"ok": True, "version": "5.0.0", "active_runs": len(_runs)}


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Return JSON errors with CORS headers so the browser sees the message."""
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": origin},
    )


app.include_router(runs.router)
app.include_router(refine.router)
app.include_router(worktree.router)
app.include_router(repos.router)
app.include_router(movements.router)
app.include_router(notes.router)
app.include_router(claude_sessions.router)
app.include_router(events.router)
